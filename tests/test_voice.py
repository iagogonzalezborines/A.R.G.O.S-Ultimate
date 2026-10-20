import asyncio
import struct
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from argos.voice import VoiceOutput


class VoiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_pcm_and_single_silent_playback_owner(self):
        # Exercise the actual process lifecycle with a silent player. No sound
        # may ever reach the user's speakers during tests.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            player = root / "silent-player"
            player.write_text("#!/usr/bin/env python3\nimport time\ntime.sleep(0.3)\n")
            player.chmod(0o755)
            audio = root / "test.wav"
            with wave.open(str(audio), "wb") as wav:
                wav.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
                wav.writeframes(struct.pack("<h", 12000) * 4800)
            voice = VoiceOutput()
            with patch("argos.voice.shutil.which", return_value=str(player)):
                try:
                    await voice.play(str(audio))
                    first = voice.process
                    await asyncio.sleep(0.03)
                    self.assertEqual(voice.state, "speaking")
                    self.assertGreater(voice.level, 0.3)
                    await voice.play(str(audio))
                    self.assertIsNotNone(first.returncode)
                    self.assertEqual(voice.generation, 2)
                    second = voice.process
                    await voice.stop()
                    self.assertIsNotNone(second.returncode)
                    self.assertEqual(voice.snapshot()["level"], 0)
                    self.assertEqual(voice.state, "idle")
                finally:
                    await voice.stop()
