"""Opt-in hands-free dialogue. Standby transcripts never leave this module.

Energy endpointing collects utterances in memory; the existing local Whisper
recognizes the invocation. No additional model is installed or downloaded.
"""
import asyncio
import math
import os
import re
import struct
import tempfile
import uuid
import wave
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from .echo import EchoCancellation
from .models import ArgosError


@dataclass
class Utterance:
    pcm: bytes
    interrupted: bool = False


class Endpoint:
    """20 ms, mono 16 kHz s16 frames; pre-roll, 800 ms silence, 20 s cap."""
    def __init__(self):
        self.reset()

    def reset(self):
        self.pre = deque(maxlen=10)
        self.frames = []
        self.silence = 0
        self.voiced = 0
        self.consecutive = 0

    def feed(self, frame):
        if len(frame) != 640:
            raise ArgosError("Trama de micrófono incompleta.")
        samples = struct.unpack("<320h", frame)
        active = math.sqrt(sum(x * x for x in samples) / 320) >= 300
        self.consecutive = self.consecutive + 1 if active else 0
        if not self.frames:
            self.pre.append(frame)
            if not active:
                return None
            self.frames = list(self.pre)
        else:
            self.frames.append(frame)
        self.voiced += int(active)
        self.silence = 0 if active else self.silence + 1
        if self.silence >= 40 or len(self.frames) >= 1000:
            result = b"".join(self.frames) if self.voiced >= 8 else None
            self.reset()
            return result
        return None


class WakeListener:
    def __init__(self, core, worker, directory):
        self.core, self.worker, self.directory = core, worker, directory
        self.enabled = False
        self.job = self.process = None
        self.project = None
        self.session = "default"
        self.state = "off"
        self.last_error = None
        self.dialogue_open = False
        self.busy = False
        self.utterances = asyncio.Queue(maxsize=4)
        self.echo = EchoCancellation()
        self.interrupt_job = None
        self.collecting_interruption = False
        self.interruptions = 0

    async def configure(self, enabled, project=None, session="default"):
        if not isinstance(enabled, bool):
            raise ArgosError("La escucha debe estar activada o desactivada.")
        await self.stop()
        if project:
            self.core.store.project(project)
        self.project, self.session, self.enabled = project, session, enabled
        if enabled:
            self.last_error = None
            self.job = asyncio.create_task(self._run())

    async def stop(self):
        self.enabled = False
        if self.job:
            self.job.cancel()
            await asyncio.gather(self.job, return_exceptions=True)
            self.job = None
        await self._close_recorder()
        self.dialogue_open = False
        self.collecting_interruption = False
        self.state = "off"
        while not self.utterances.empty():
            self.utterances.get_nowait()
            self.utterances.task_done()

    async def _close_recorder(self):
        if self.process and self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), 3)
            except TimeoutError:
                self.process.kill()
                await self.process.wait()
        self.process = None

    def available(self):
        # Only a verified AEC path may listen over our own playback.
        return (self.core.capture.state in ("idle", "error")
                and (self.echo.active or (self.core.speech.state == "idle"
                     and getattr(self.core.voice, "state", "idle") != "speaking"))
                and not getattr(self.worker, "preparing", False))

    async def _capture_loop(self):
        from .speech import input_devices
        target = []
        device = self.core.capture.input_device
        if device:
            if device not in [d["id"] for d in await input_devices()]:
                raise ArgosError("El micrófono seleccionado no está conectado.")
            target = ["--target", device]
        if self.echo.active:
            target = ["--target", self.echo.source]
        self.process = await asyncio.create_subprocess_exec(
            "pw-record", *target, "--raw", "--rate=16000", "--channels=1", "--format=s16", "-",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        endpoint = Endpoint()
        while self.enabled:
            frame = await self.process.stdout.readexactly(640)
            if not self.available():
                endpoint.reset()
                self.state = "paused"
                continue
            self.state = "conversation" if self.dialogue_open else "listening_for_argos"
            utterance = endpoint.feed(frame)
            output_busy = (self.core.speech.state in ("thinking", "speaking")
                           or getattr(self.core.voice, "state", "idle") in ("thinking", "speaking"))
            if (self.echo.active and self.dialogue_open and output_busy
                    and endpoint.consecutive >= 8 and not self.collecting_interruption):
                # 160 ms of sustained post-AEC activity rejects isolated clicks.
                # Keep pre-roll and continue reading while TTS is cancelled.
                self.collecting_interruption = True
                self.core.speech.paused = True
                self.interruptions += 1
                self.interrupt_job = asyncio.create_task(self.core.speech.interrupt())
            if utterance:
                # Keep decoding independent of capture: never replay a backlog
                # of playback frames after a slow model response.
                if self.utterances.full():
                    self.last_error = "Hay demasiados turnos pendientes; repite la última frase."
                else:
                    self.utterances.put_nowait(Utterance(utterance, self.collecting_interruption))
                self.collecting_interruption = False

    async def _turn_loop(self):
        while self.enabled:
            utterance = await self.utterances.get()
            try:
                # Without AEC a response must finish before local recognition.
                speech_job = getattr(self.core.speech, "job", None)
                if speech_job and not speech_job.done():
                    try:
                        await asyncio.shield(speech_job)
                    except asyncio.CancelledError:
                        # Barge-in cancels speech, not this conversation consumer.
                        if asyncio.current_task().cancelling():
                            raise
                if self.interrupt_job:
                    await self.interrupt_job
                    self.interrupt_job = None
                await self.process_audio(utterance.pcm, interrupted=utterance.interrupted)
            except ArgosError:
                # An invalid command/approval must not close the conversation.
                self.last_error = "No he podido procesar ese turno. Revisa el diagnóstico o repite la petición."
                self.core.speech.enqueue(self.last_error, language=self.core.speech.language)
            finally:
                self.utterances.task_done()

    async def _run(self):
        jobs = []
        try:
            from .speech import input_devices
            device = self.core.capture.input_device
            if device and device not in [d["id"] for d in await input_devices()]:
                raise ArgosError("El micrófono seleccionado no está conectado.")
            self.state = "preparing"
            self.core.speech.paused = True
            if await self.echo.start(device):
                self.core.voice.target = self.echo.sink
                jobs.append(asyncio.create_task(self.echo.watch()))
            self.core.speech.paused = False
            self.core.speech.resume_queue()
            jobs.extend([asyncio.create_task(self._capture_loop()), asyncio.create_task(self._turn_loop())])
            await asyncio.gather(*jobs)
        except asyncio.CancelledError:
            raise
        except (ArgosError, OSError, ValueError, asyncio.IncompleteReadError):
            self.last_error = "La escucha de Argos falló. Revisa voz y micrófono; reactívala para reintentar."
            self.state = "error"
            self.enabled = False
            self.dialogue_open = False
        finally:
            for job in jobs:
                job.cancel()
            await asyncio.gather(*jobs, return_exceptions=True)
            await self._close_recorder()
            if self.interrupt_job:
                await asyncio.gather(self.interrupt_job, return_exceptions=True)
                self.interrupt_job = None
            if getattr(self.core.voice, "target", None) == self.echo.sink:
                # Stop audio before its AEC route disappears; never reroute a
                # currently speaking stream to an unfiltered speaker.
                await self.core.speech.stop()
                self.core.voice.target = None
            await self.echo.stop()
            self.collecting_interruption = False
            while not self.utterances.empty():
                self.utterances.get_nowait()
                self.utterances.task_done()
            self.core.speech.paused = False
            self.core.speech.resume_queue()

    async def process_audio(self, pcm, interrupted=False):
        fd, path = tempfile.mkstemp(prefix="wake-", suffix=".wav", dir=self.directory)
        os.close(fd)
        self.busy = True
        self.core.speech.paused = True
        try:
            with wave.open(path, "wb") as file:
                file.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
                file.writeframes(pcm)
            result = await self.worker.request({"op": "transcribe", "path": path,
                                               "language": "auto" if self.core.speech.automatic_language else self.core.speech.language,
                                               "previous_language": self.core.speech.language})
            await self.handle_transcript(result, interrupted=interrupted)
        finally:
            Path(path).unlink(missing_ok=True)
            self.busy = False
            self.core.speech.paused = self.collecting_interruption or not self.utterances.empty()
            self.core.speech.resume_queue()

    async def handle_transcript(self, result, interrupted=False):
        from .language import normalized
        text = result.get("text", "").strip()
        # A quoted, negated or embedded mention does not open a conversation.
        match = re.match(r"^[¿¡]?(?:hey[, ]+|oye[, ]+)?argos\b[\s,.:;!?¿¡-]*(.*)$", text, re.I)
        if match:
            self.dialogue_open = True
            text = match[1].strip()
            if not text:
                text = result["text"].strip()  # The invocation is a real conversational turn.
        elif not self.dialogue_open:
            return  # Standby speech is never persisted or forwarded.
        if not text:
            return
        dismiss = normalized(text) in ("eso es todo", "eso es todo gracias", "terminamos", "hasta luego",
                                       "vuelve a esperar", "that's all", "that is all", "that's all thanks",
                                       "we're done", "we are done", "go back to standby", "goodbye")
        if dismiss:
            self.dialogue_open = False
            # Discard already queued turns from this dialogue, not background tasks.
            while not self.utterances.empty():
                self.utterances.get_nowait()
                self.utterances.task_done()
        await self.core.request({"method": "say", "text": text, "project": self.project,
                                 "session": self.session, "request_id": uuid.uuid4().hex, "speak": True,
                                 "conversation": True, "end_dialogue": dismiss,
                                 "speech_interrupted": interrupted,
                                 "detected_language": result.get("language"),
                                 "language_probability": result.get("language_probability", 0.0)})
