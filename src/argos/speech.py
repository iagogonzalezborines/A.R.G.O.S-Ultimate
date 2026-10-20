"""Local STT/TTS process and push-to-talk. Audio files are temporary and private."""
import asyncio
import contextlib
import json
import os
import re
import signal
import tempfile
import uuid
from pathlib import Path

from .models import ArgosError


VOICE_PYTHON = Path.home() / ".local/share/argos/voice-env/bin/python"


class VoiceWorker:
    def __init__(self):
        self.process = None
        self.lock = asyncio.Lock()

    async def request(self, message):
        async with self.lock:
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
                line = await asyncio.wait_for(self.process.stdout.readline(), 120)
                result = json.loads(line)
                if not result.get("ok"):
                    raise ArgosError(result.get("error", "Falló la voz."))
                return result
            except BaseException:
                await self.close()
                raise

    async def close(self):
        if self.process and self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), 3)
            except TimeoutError:
                self.process.kill()
                await self.process.wait()
        self.process = None


class Speech:
    def __init__(self, worker, output, directory):
        self.worker, self.output, self.directory = worker, output, directory
        self.queue = asyncio.Queue(maxsize=16)
        self.job = None
        self.state = "idle"
        self.language = "es"
        self.last_error = None
        self.paused = False

    def enqueue(self, text):
        # Spoken output is concise; the full structured result remains in the task.
        text = re.sub(r"https?://\S+", "enlace en los detalles", text)
        text = re.sub(r"[`*_#]", "", text).strip()
        if text and not self.queue.full():
            self.queue.put_nowait(text[:1200])
            self.resume_queue()

    def resume_queue(self):
        if not self.paused and not self.queue.empty() and (self.job is None or self.job.done()):
            self.job = asyncio.create_task(self._run())

    async def _run(self):
        try:
            while not self.queue.empty():
                text = self.queue.get_nowait()
                fd, filename = tempfile.mkstemp(prefix="speech-", suffix=".wav", dir=self.directory)
                os.close(fd)
                try:
                    self.state = "thinking"
                    await self.worker.request({"op": "synthesize", "text": text,
                                               "language": self.language, "path": filename})
                    await self.output.play(filename)
                    if self.output.job:
                        await self.output.job
                    self.last_error = None
                except (ArgosError, OSError, ValueError) as error:
                    self.last_error = str(error)
                    self.state = "error"
                finally:
                    Path(filename).unlink(missing_ok=True)
                    self.queue.task_done()
        finally:
            if self.state != "error":
                self.state = "idle"

    async def stop(self):
        if self.job:
            self.job.cancel()
            await asyncio.gather(self.job, return_exceptions=True)
            self.job = None
        while not self.queue.empty():
            self.queue.get_nowait()
            self.queue.task_done()
        await self.output.stop()
        self.state = "idle"


class Capture:
    def __init__(self, core, worker, directory):
        self.core, self.worker, self.directory = core, worker, directory
        self.state, self.process, self.path = "idle", None, None
        self.job, self.timer = None, None
        self.lock = asyncio.Lock()
        self.project = None
        self.last_error = None

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
                self.process = await asyncio.create_subprocess_exec(
                    "pw-record", "--rate=16000", "--channels=1", "--format=s16", self.path,
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
                await asyncio.sleep(0.1)
                if self.process.returncode is not None:
                    raise ArgosError("PipeWire no pudo abrir el micrófono.")
            except BaseException:
                await self._discard()
                self.core.speech.paused = False
                self.core.speech.resume_queue()
                self.state = "error"
                self.last_error = "No se pudo abrir el micrófono."
                raise
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
        try:
            result = await self.worker.request({"op": "transcribe", "path": self.path})
            self.core.speech.language = "en" if result["language"] == "en" else "es"
            if result["text"]:
                await self.core.request({"method": "say", "text": result["text"], "project": self.project,
                                         "session": "default", "request_id": uuid.uuid4().hex, "speak": True})
            else:
                self.core.speech.enqueue("No he entendido la petición.")
            self.last_error = None
        except (ArgosError, OSError, ValueError) as error:
            self.last_error = str(error)
            self.core.speech.enqueue("No he podido procesar la petición. Revisa el diagnóstico de voz.")
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
