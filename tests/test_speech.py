import asyncio
import tempfile
import unittest
import wave
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from pathlib import Path

from argos.speech import Speech, Capture
from argos.models import ArgosError


class SpeechTests(unittest.IsolatedAsyncioTestCase):
    async def test_auto_recognition_passes_evidence_to_core_without_mutating_voice(self):
        with tempfile.TemporaryDirectory() as temp:
            speech = Speech(None, None, Path(temp))
            core = SimpleNamespace(speech=speech, request=AsyncMock())
            worker = SimpleNamespace(request=AsyncMock(return_value={"text": "hola", "language": "en"}))
            capture = Capture(core, worker, Path(temp))
            capture.path = str(Path(temp) / "recording.wav")
            Path(capture.path).touch()
            await capture._transcribe()
            self.assertEqual(worker.request.call_args.args[0]["language"], "auto")
            self.assertEqual(speech.language, "es")
            self.assertEqual(core.request.call_args.args[0]["text"], "hola")
            self.assertEqual(core.request.call_args.args[0]["detected_language"], "en")
            self.assertEqual(list(Path(temp).iterdir()), [])

    async def test_selected_microphone_is_passed_to_recorder(self):
        with tempfile.TemporaryDirectory() as temp:
            output = SimpleNamespace(stop=AsyncMock())
            speech = Speech(None, output, Path(temp))
            core = SimpleNamespace(speech=speech)
            capture = Capture(core, None, Path(temp))
            capture.input_device = "steelseries-input"
            proc = SimpleNamespace(returncode=None, wait=AsyncMock(return_value=0))
            proc.send_signal = lambda _: setattr(proc, "returncode", 0)
            with patch("argos.speech.input_devices", AsyncMock(return_value=[{"id": "steelseries-input"}])), \
                 patch("argos.speech.asyncio.create_subprocess_exec", AsyncMock(return_value=proc)) as spawn:
                try:
                    await capture.toggle()
                    argv = spawn.call_args.args
                    self.assertEqual(argv[argv.index("--target") + 1], "steelseries-input")
                    self.assertEqual(capture.state, "listening")
                finally:
                    await capture.cancel()

    async def test_missing_selected_microphone_never_falls_back(self):
        with tempfile.TemporaryDirectory() as temp:
            speech = Speech(None, SimpleNamespace(stop=AsyncMock()), Path(temp))
            capture = Capture(SimpleNamespace(speech=speech), None, Path(temp))
            capture.input_device = "disconnected-headset"
            with patch("argos.speech.input_devices", AsyncMock(return_value=[{"id": "webcam"}])), \
                 patch("argos.speech.asyncio.create_subprocess_exec", AsyncMock()) as spawn:
                with self.assertRaises(ArgosError):
                    await capture.toggle()
                spawn.assert_not_called()
            self.assertIn("no está conectado", capture.last_error)
            self.assertEqual(capture.state, "error")
            self.assertFalse(speech.paused)
            self.assertEqual(list(Path(temp).iterdir()), [])

    async def test_capture_pause_keeps_notifications_out_of_microphone(self):
        with tempfile.TemporaryDirectory() as temp:
            speech = Speech(None, None, Path(temp))
            speech.paused = True
            speech.enqueue("Aviso de otra tarea.")
            self.assertIsNone(speech.job)
            self.assertEqual(speech.queue.qsize(), 1)

    async def test_cancelled_synthesis_removes_audio_and_pending_speech(self):
        entered = asyncio.Event()
        class Worker:
            async def request(self, request):
                entered.set()
                await asyncio.sleep(60)
        class Output:
            async def stop(self):
                pass
        with tempfile.TemporaryDirectory() as temp:
            speech = Speech(Worker(), Output(), Path(temp))
            speech.enqueue("Primero.")
            speech.enqueue("Segundo.")
            await entered.wait()
            self.assertEqual(len(list(Path(temp).iterdir())), 1)
            await speech.stop()
            self.assertEqual(list(Path(temp).iterdir()), [])
            self.assertTrue(speech.queue.empty())
            self.assertEqual(speech.state, "idle")

    async def test_speech_is_serial_and_leaves_no_recordings(self):
        observed = []
        class Worker:
            async def request(self, request):
                observed.append(request["text"])
                with wave.open(request["path"], "wb") as file:
                    file.setnchannels(1)
                    file.setsampwidth(2)
                    file.setframerate(16000)
                    file.writeframes(b"\0" * 100)
                return {"ok": True}
        class Output:
            job = None
            async def play(self, path):
                self.job = asyncio.create_task(asyncio.sleep(0.01))
            async def stop(self):
                pass
        with tempfile.TemporaryDirectory() as temp:
            speech = Speech(Worker(), Output(), Path(temp))
            speech.enqueue("Uno.")
            speech.enqueue("Dos.")
            await speech.job
            self.assertEqual(observed, ["Uno.", "Dos."])
            self.assertEqual(list(Path(temp).iterdir()), [])

    async def test_queued_utterances_keep_their_own_language(self):
        observed = []
        class Worker:
            async def request(self, message):
                observed.append((message["text"], message["language"]))
                Path(message["path"]).touch()
        class Output:
            job = None
            async def play(self, path):
                self.job = asyncio.create_task(asyncio.sleep(0))
        with tempfile.TemporaryDirectory() as temp:
            speech = Speech(Worker(), Output(), Path(temp))
            speech.paused = True
            speech.enqueue("Hola.", language="es")
            speech.language = "en"
            speech.enqueue("Hello.", language="en")
            speech.language = "es"
            speech.paused = False
            speech.resume_queue()
            await speech.job
            self.assertEqual(observed, [("Hola.", "es"), ("Hello.", "en")])
