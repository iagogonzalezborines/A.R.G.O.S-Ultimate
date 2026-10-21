"""Local STT/TTS process and push-to-talk. Audio files are temporary and private."""
import asyncio
import base64
import contextlib
import json
import os
import re
import signal
import tempfile
import time
import uuid
from pathlib import Path

from .models import ArgosError
from .language import localize


VOICE_PYTHON = Path.home() / ".local/share/argos/voice-env/bin/python"


async def input_devices():
    from .linux_tools import process
    code, output, _ = await process(["pactl", "-f", "json", "list", "sources"])
    if code:
        raise ArgosError("No se pudo consultar la lista de micrófonos.")
    return [{"id": item["name"], "name": item.get("description", item["name"])}
            for item in json.loads(output) if not item["name"].endswith(".monitor")]


class VoiceWorker:
    def __init__(self):
        self.process = None
        self.lock = asyncio.Lock()
        self.ready = False
        self.preparing = False
        self.last_error = None

    async def _responses(self, message):
        async with self.lock:
            completed = False
            if not self.process or self.process.returncode is not None:
                if not VOICE_PYTHON.exists():
                    raise ArgosError("Falta instalar el entorno local de voz.")
                self.process = await asyncio.create_subprocess_exec(
                    str(VOICE_PYTHON), str(Path(__file__).with_name("voice_worker.py")),
                    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL)
            try:
                self.process.stdin.write(json.dumps(message).encode() + b"\n")
                await self.process.stdin.drain()
                while True:
                    line = await asyncio.wait_for(self.process.stdout.readline(), 120)
                    result = json.loads(line)
                    if not result.get("ok"):
                        raise ArgosError(result.get("error", "Falló la voz."))
                    if "chunk" not in result:
                        self.ready = True
                        self.last_error = None
                        completed = True
                        yield result
                        break
                    yield result
            except BaseException:
                if not completed:
                    await self.close()
                raise

    async def request(self, message):
        async with contextlib.aclosing(self._responses(message)) as responses:
            async for result in responses:
                if "chunk" not in result:
                    return result

    async def chunks(self, text, language):
        message = {"op": "synthesize", "text": text, "language": language, "stream": True}
        async with contextlib.aclosing(self._responses(message)) as responses:
            async for result in responses:
                if "chunk" in result:
                    if result.get("rate") != 24000:
                        raise ArgosError("Frecuencia de síntesis no admitida.")
                    pcm = base64.b64decode(result["chunk"], validate=True)
                    if not pcm or len(pcm) % 2:
                        raise ArgosError("El modelo devolvió audio incompleto.")
                    yield pcm

    async def warmup(self, language):
        self.preparing = True
        try:
            await self.request({"op": "warmup", "language": language})
        except (ArgosError, OSError, ValueError, TimeoutError) as error:
            self.last_error = str(error)
        finally:
            self.preparing = False

    async def close(self):
        if self.process and self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), 3)
            except TimeoutError:
                self.process.kill()
                await self.process.wait()
        self.process = None
        self.ready = False


class Speech:
    def __init__(self, worker, output, directory):
        self.worker, self.output, self.directory = worker, output, directory
        self.queue = asyncio.Queue(maxsize=16)
        self.job = None
        self.state = "idle"
        self.language = "es"
        self.automatic_language = True
        self.last_error = None
        self.paused = False
        self.first_audio_ms = None

    def enqueue(self, text, language=None):
        language = language or self.language
        # Brevity belongs to the conversation contract, never a character slice.
        text = re.sub(r"https?://\S+", "link in the details" if language == "en" else "enlace en los detalles", text)
        text = re.sub(r"[`*_#]", "", text).strip()
        if text and not self.queue.full():
            self.queue.put_nowait((text, language))
            self.resume_queue()

    def resume_queue(self):
        if not self.paused and not self.queue.empty() and (self.job is None or self.job.done()):
            self.job = asyncio.create_task(self._run())

    async def _run(self):
        try:
            while not self.queue.empty() and not self.paused:
                text, language = self.queue.get_nowait()
                try:
                    self.state = "thinking"
                    started = time.monotonic()
                    self.first_audio_ms = None
                    def first_audio():
                        self.first_audio_ms = round((time.monotonic() - started) * 1000)
                        self.state = "speaking"
                    await self.output.play_stream(self.worker.chunks(text, language), first_audio)
                    if self.output.job:
                        await self.output.job
                    self.last_error = None
                except (ArgosError, OSError, ValueError, TimeoutError) as error:
                    self.last_error = str(error)
                    self.state = "error"
                finally:
                    self.queue.task_done()
        finally:
            if self.state != "error":
                self.state = "idle"

    async def stop(self):
        await self.output.stop()
        if self.job:
            self.job.cancel()
            await asyncio.gather(self.job, return_exceptions=True)
            self.job = None
        while not self.queue.empty():
            self.queue.get_nowait()
            self.queue.task_done()
        self.state = "idle"

    async def interrupt(self):
        """Barge-in only stops speech; the listener owns when speech resumes."""
        self.paused = True
        await self.stop()


class Capture:
    def __init__(self, core, worker, directory):
        self.core, self.worker, self.directory = core, worker, directory
        self.state, self.process, self.path = "idle", None, None
        self.job, self.timer = None, None
        self.lock = asyncio.Lock()
        self.project = None
        self.session = "default"
        self.last_error = None
        self.input_device = None
        self.timings = {}

    async def toggle(self, project=None):
        async with self.lock:
            if self.state == "listening":
                await self._finish()
                return
            if self.state == "thinking":
                return
            if project:
                self.core.store.project(project)
            self.core.speech.paused = True
            await self.core.speech.stop()
            self.project = project
            fd, self.path = tempfile.mkstemp(prefix="microphone-", suffix=".wav", dir=self.directory)
            os.close(fd)
            try:
                target = []
                if self.input_device:
                    if self.input_device not in [item["id"] for item in await input_devices()]:
                        raise ArgosError("El micrófono seleccionado no está conectado.")
                    target = ["--target", self.input_device]
                self.process = await asyncio.create_subprocess_exec(
                    "pw-record", *target, "--rate=16000", "--channels=1", "--format=s16", self.path,
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
                await asyncio.sleep(0.1)
                if self.process.returncode is not None:
                    raise ArgosError("PipeWire no pudo abrir el micrófono.")
            except BaseException as error:
                await self._discard()
                self.core.speech.paused = False
                self.core.speech.resume_queue()
                self.state = "error"
                self.last_error = str(error) if isinstance(error, ArgosError) else "No se pudo abrir el micrófono."
                raise
            self.last_error = None
            self.state = "listening"
            self.timer = asyncio.create_task(self._limit())

    async def _limit(self):
        await asyncio.sleep(30)
        async with self.lock:
            if self.state == "listening":
                await self._finish()

    async def _stop_recorder(self):
        if self.process and self.process.returncode is None:
            self.process.send_signal(signal.SIGINT)
            try:
                await asyncio.wait_for(self.process.wait(), 3)
            except TimeoutError:
                self.process.kill()
                await self.process.wait()
        self.process = None

    async def _finish(self):
        if self.timer and self.timer is not asyncio.current_task():
            self.timer.cancel()
            await asyncio.gather(self.timer, return_exceptions=True)
        self.timer = None
        await self._stop_recorder()
        self.state = "thinking"
        self.job = asyncio.create_task(self._transcribe())

    async def _transcribe(self):
        started = time.monotonic()
        self.timings = {}
        try:
            result = await self.worker.request({"op": "transcribe", "path": self.path,
                                               "language": "auto" if self.core.speech.automatic_language else self.core.speech.language,
                                               "previous_language": self.core.speech.language})
            self.timings["stt_ms"] = round((time.monotonic() - started) * 1000)
            if result["text"]:
                dispatched = time.monotonic()
                await self.core.request({"method": "say", "text": result["text"], "project": self.project,
                                         "session": self.session, "request_id": uuid.uuid4().hex, "speak": True,
                                         "detected_language": result.get("language"),
                                         "language_probability": result.get("language_probability", 0.0)})
                self.timings["dispatch_ms"] = round((time.monotonic() - dispatched) * 1000)
            else:
                self.core.speech.enqueue(localize("No he entendido la petición.", self.core.speech.language))
            self.last_error = None
        except (ArgosError, OSError, ValueError) as error:
            self.last_error = str(error)
            self.core.speech.enqueue(localize("No he podido procesar la petición. Revisa el diagnóstico de voz.",
                                             self.core.speech.language))
        finally:
            if self.path:
                Path(self.path).unlink(missing_ok=True)
                self.path = None
            self.state = "error" if self.last_error else "idle"
            self.core.speech.paused = False
            self.core.speech.resume_queue()

    async def _discard(self):
        await self._stop_recorder()
        if self.path:
            Path(self.path).unlink(missing_ok=True)
            self.path = None

    async def cancel(self):
        async with self.lock:
            for job in (self.timer, self.job):
                if job:
                    job.cancel()
                    await asyncio.gather(job, return_exceptions=True)
            self.timer = self.job = None
            await self._discard()
            self.state = "idle"
            self.core.speech.paused = False
            self.core.speech.resume_queue()
