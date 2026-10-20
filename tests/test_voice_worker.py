import contextlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from argos.speech import VoiceWorker


FAKE = '''#!/usr/bin/env python3
import base64,json,sys,time
for line in sys.stdin:
    request=json.loads(line)
    if request.get("stream"):
        print(json.dumps({"ok":True,"chunk":base64.b64encode(b"\\0"*3840).decode(),"rate":24000}),flush=True)
        if request["text"]=="block": time.sleep(60)
    print(json.dumps({"ok":True}),flush=True)
'''


class WorkerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        executable = Path(self.temp.name) / "fake-voice"
        executable.write_text(FAKE)
        executable.chmod(0o700)
        self.python = patch("argos.speech.VOICE_PYTHON", executable)
        self.python.start()
        self.worker = VoiceWorker()

    async def asyncTearDown(self):
        await self.worker.close()
        self.python.stop()
        self.temp.cleanup()

    async def test_finished_stream_and_requests_reuse_warm_process(self):
        await self.worker.warmup("es")
        child = self.worker.process
        chunks = [data async for data in self.worker.chunks("hola", "es")]
        self.assertEqual(chunks, [b"\0" * 3840])
        self.assertTrue(self.worker.ready)
        await self.worker.request({"op": "warmup"})
        self.assertIs(self.worker.process, child)
        self.assertIsNone(child.returncode)

    async def test_abandoned_stream_reaps_process_and_next_request_restarts(self):
        async with contextlib.aclosing(self.worker.chunks("block", "es")) as chunks:
            await anext(chunks)
            child = self.worker.process
        self.assertIsNotNone(child.returncode)
        self.assertFalse(self.worker.ready)
        await self.worker.warmup("en")
        self.assertTrue(self.worker.ready)
        self.assertIsNot(self.worker.process, child)
