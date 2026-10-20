import asyncio
import tempfile
import unittest
import wave
from pathlib import Path

from argos.speech import Speech


class SpeechTests(unittest.IsolatedAsyncioTestCase):
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
