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
import time
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
    generation: int | None = None


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
        self.collecting_input = False
        self.input_generation = 0
        self.input_idle = asyncio.Event()
        self.input_idle.set()
        self.interruptions = 0
        # Aggregate diagnostics only: never expose standby text or retain PCM.
        self.diagnostics = {"frames": 0, "active_frames": 0, "utterances": 0,
                            "empty_transcripts": 0, "unmatched_invocations": 0,
                            "activation_only": 0,
                            "accepted_turns": 0, "completed_turns": 0, "failed_turns": 0,
                            "suppressed_replies": 0, "merged_segments": 0, "discarded_segments": 0,
                            "last_result": "waiting_for_audio"}

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
        self.collecting_input = False
        self.input_idle.set()
        self.input_generation += 1  # Replies from the previous listener cannot resume.
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
                self.collecting_input = False
                self.input_idle.set()
                self.state = "paused"
                continue
            self.state = "conversation" if self.dialogue_open else "listening_for_argos"
            utterance = endpoint.feed(frame)
            self.diagnostics["frames"] += 1
            self.diagnostics["active_frames"] += int(endpoint.consecutive > 0)
            output_busy = (self.core.speech.state in ("thinking", "speaking")
                           or getattr(self.core.voice, "state", "idle") in ("thinking", "speaking"))
            if endpoint.consecutive >= 8 and not self.collecting_input:
                # Claim the conversational floor even during STT/inference,
                # before there is any output to interrupt. Isolated clicks do
                # not advance the generation or suppress a response.
                self.collecting_input = True
                self.input_generation += 1
                self.input_idle.clear()
                if self.dialogue_open:
                    self.core.speech.paused = True
                    if self.echo.active and (output_busy or self.busy or not self.utterances.empty()):
                        self.collecting_interruption = True
                        self.interruptions += 1
                        if not self.interrupt_job or self.interrupt_job.done():
                            self.interrupt_job = asyncio.create_task(self.core.speech.interrupt())
            if utterance:
                self.diagnostics["utterances"] += 1
                # Keep decoding independent of capture: never replay a backlog
                # of playback frames after a slow model response.
                if self.utterances.full():
                    # A bounded queue must retain the newest correction, not
                    # discard it while preserving the oldest unprocessed audio.
                    self.utterances.get_nowait()
                    self.utterances.task_done()
                    self.diagnostics["discarded_segments"] += 1
                    self.last_error = "Se ha descartado audio antiguo de la cola; revisa las peticiones pendientes."
                self.utterances.put_nowait(Utterance(
                    utterance, self.collecting_interruption, self.input_generation))
                self.collecting_interruption = False
                self.collecting_input = False
                self.input_idle.set()

    async def _turn_loop(self):
        while self.enabled:
            utterance = await self.utterances.get()
            consumed = 1
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
                await self.input_idle.wait()
                # Backlogged segments belong to one continuing intervention.
                # Preserve their words and order instead of answering each
                # fragment separately. Memory stays bounded by the input queue.
                segments = [utterance.pcm]
                if utterance.generation is not None:
                    while not self.utterances.empty():
                        following = self.utterances.get_nowait()
                        consumed += 1
                        segments.append(following.pcm)
                        utterance = Utterance(b"", utterance.interrupted or following.interrupted,
                                              following.generation)
                    self.diagnostics["merged_segments"] += consumed - 1
                await self.process_audio(b"".join(segments), interrupted=utterance.interrupted,
                                         generation=utterance.generation)
            except ArgosError as error:
                # An invalid command/approval must not close the conversation.
                # ArgosError is already a safe public error, never a raw provider
                # exception. Keep the actual cause and the current turn language.
                from .language import localize
                self.last_error = localize(str(error), self.core.speech.language)
                self.diagnostics["failed_turns"] += 1
                self.diagnostics["last_result"] = "failed"
                if (not self.collecting_input and self.utterances.empty()
                        and (utterance.generation is None or utterance.generation == self.input_generation)):
                    self.core.speech.enqueue(self.last_error, language=self.core.speech.language)
                else:
                    self.diagnostics["suppressed_replies"] += 1
            finally:
                for _ in range(consumed):
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
            self.collecting_input = False
            self.input_idle.set()
            while not self.utterances.empty():
                self.utterances.get_nowait()
                self.utterances.task_done()
            self.core.speech.paused = False
            self.core.speech.resume_queue()

    async def process_audio(self, pcm, interrupted=False, generation=None):
        started = time.monotonic()
        self.timings = {}
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
            self.timings["stt_ms"] = round((time.monotonic() - started) * 1000)
            dispatched = time.monotonic()
            try:
                await self.handle_transcript(result, interrupted=interrupted, generation=generation)
            finally:
                self.timings["dispatch_ms"] = round((time.monotonic() - dispatched) * 1000)
        finally:
            Path(path).unlink(missing_ok=True)
            self.busy = False
            # A new intervention owns the floor until it has been processed.
            self.core.speech.paused = self.collecting_input or not self.utterances.empty()
            self.core.speech.resume_queue()

    async def handle_transcript(self, result, interrupted=False, generation=None):
        from .language import normalized, voice_invocation
        text = result.get("text", "").strip()
        if not text:
            self.diagnostics["empty_transcripts"] += 1
            self.diagnostics["last_result"] = "empty_transcript"
            return
        # A quoted, negated or embedded mention does not open a conversation.
        content = voice_invocation(text)
        if content is not None:
            self.dialogue_open = True
            text = content
            if not text:
                # A pause after the name creates a separate acoustic segment.
                # Opening the microphone dialogue is local control, not a model
                # request that should block the actual question behind it.
                self.diagnostics["activation_only"] += 1
                self.diagnostics["last_result"] = "activated"
                return
        elif not self.dialogue_open:
            self.diagnostics["unmatched_invocations"] += 1
            self.diagnostics["last_result"] = "invocation_not_recognized"
            return  # Standby speech is never persisted or forwarded.
        if not text:
            return
        self.diagnostics["accepted_turns"] += 1
        self.diagnostics["last_result"] = "accepted"
        farewell = re.sub(r"[, ]+argos$", "", normalized(text))
        dismiss = farewell in ("eso es todo", "eso es todo gracias", "terminamos", "hasta luego",
                                       "vuelve a esperar", "that's all", "that is all", "that's all thanks",
                                       "we're done", "we are done", "go back to standby", "goodbye")
        if dismiss:
            self.dialogue_open = False
            # Discard already queued turns from this dialogue, not background tasks.
            while not self.utterances.empty():
                self.utterances.get_nowait()
                self.utterances.task_done()
        from .router import Router
        dispatch = self.core.voice_control if Router().resolve(text).kind == "stop_listening" else self.core.request
        await dispatch({"method": "say", "text": text, "project": self.project,
                                 "session": self.session, "request_id": uuid.uuid4().hex, "speak": True,
                                 "conversation": True, "end_dialogue": dismiss,
                                 **({"voice_generation": generation} if generation is not None else {}),
                                 "speech_interrupted": interrupted,
                                 "detected_language": result.get("language"),
                                 "language_probability": result.get("language_probability", 0.0)})
        self.diagnostics["completed_turns"] += 1
        self.last_error = None
