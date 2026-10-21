import asyncio
import struct
import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from argos.voice import VoiceOutput
from argos.models import ArgosError


class VoiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_stop_silences_player_before_slow_generator_cleanup(self):
        started, closing, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
        async def chunks():
            try:
                yield b"\0" * 11520
                await asyncio.Event().wait()
            finally:
                closing.set()
                await release.wait()
        with tempfile.TemporaryDirectory() as temp:
            player = Path(temp) / "silent-player"
            player.write_text("#!/usr/bin/env python3\nimport sys\nsys.stdin.buffer.read()\n")
            player.chmod(0o700)
            voice = VoiceOutput()
            with patch("argos.voice.shutil.which", return_value=str(player)):
                await voice.play_stream(chunks(), started.set)
                await asyncio.wait_for(started.wait(), 2)
                child = voice.process
                stopping = asyncio.create_task(voice.stop())
                try:
                    await asyncio.wait_for(closing.wait(), 2)
                    await asyncio.wait_for(child.wait(), 2)
                    self.assertIsNotNone(child.returncode)
                    self.assertFalse(stopping.done())
                finally:
                    release.set()
                    await stopping

    async def test_aec_routes_stream_and_wav_to_same_reference_sink(self):
        child = SimpleNamespace(returncode=0, wait=AsyncMock(return_value=0),
                                stdin=SimpleNamespace(write=Mock(), drain=AsyncMock(), close=Mock()))
        async def chunks():
            yield b"\0" * 960
        with tempfile.TemporaryDirectory() as temp:
            audio = Path(temp) / "voice.wav"
            with wave.open(str(audio), "wb") as wav:
                wav.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
                wav.writeframes(b"\0" * 640)
            voice = VoiceOutput()
            voice.target = "argos-reference"
            with patch("argos.voice.shutil.which", return_value="/usr/bin/pw-play"), \
                 patch("asyncio.create_subprocess_exec", AsyncMock(return_value=child)) as spawn:
                await voice.play_stream(chunks())
                await voice.job
                self.assertEqual(spawn.call_args.args[:3], ("/usr/bin/pw-play", "--target", "argos-reference"))
                await voice.play(audio)
                await voice.job
                self.assertEqual(spawn.call_args.args[:3], ("/usr/bin/pw-play", "--target", "argos-reference"))
                await voice.stop()

    async def test_aec_does_not_fall_back_to_unfiltered_alsa(self):
        voice = VoiceOutput()
        voice.target = "argos-reference"
        async def chunks():
            yield b"\0" * 960
        with patch("argos.voice.shutil.which", side_effect=lambda name: "/usr/bin/aplay" if name == "aplay" else None), \
             patch("asyncio.create_subprocess_exec", AsyncMock()) as spawn:
            with self.assertRaises(ArgosError):
                await voice.play_stream(chunks())
            spawn.assert_not_called()

    async def test_initial_buffer_waits_for_more_audio_and_preserves_every_byte(self):
        initial, release = asyncio.Event(), asyncio.Event()
        pcm = struct.pack("<h", 1234) * 8000 + struct.pack("<h", 2345) * 137
        async def chunks():
            yield pcm[:3840]
            initial.set()
            await release.wait()
            yield pcm[3840:11520]
            yield pcm[11520:]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            recorded = root / "received.pcm"
            player = root / "silent-player"
            player.write_text("#!/usr/bin/env python3\nimport sys,pathlib\n"
                              f"pathlib.Path({str(recorded)!r}).write_bytes(sys.stdin.buffer.read())\n")
            player.chmod(0o700)
            voice = VoiceOutput()
            with patch("argos.voice.shutil.which", return_value=str(player)):
                try:
                    await voice.play_stream(chunks())
                    await asyncio.wait_for(initial.wait(), 2)
                    self.assertIsNone(voice.process)
                    self.assertEqual(voice.state, "thinking")
                    release.set()
                    await asyncio.wait_for(voice.job, 2)
                    self.assertEqual(recorded.read_bytes(), pcm)
                    self.assertEqual(voice.state, "idle")
                finally:
                    await voice.stop()

    async def test_short_utterance_below_buffer_threshold_is_not_discarded(self):
        pcm = struct.pack("<h", 2345) * 480
        async def chunks():
            yield pcm
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            recorded = root / "received.pcm"
            player = root / "silent-player"
            player.write_text("#!/usr/bin/env python3\nimport sys,pathlib\n"
                              f"pathlib.Path({str(recorded)!r}).write_bytes(sys.stdin.buffer.read())\n")
            player.chmod(0o700)
            voice = VoiceOutput()
            with patch("argos.voice.shutil.which", return_value=str(player)):
                await voice.play_stream(chunks())
                await voice.job
                self.assertEqual(recorded.read_bytes(), pcm)
                await voice.stop()

    async def test_stream_starts_before_generation_finishes_and_stop_closes_source(self):
        started, closed = asyncio.Event(), asyncio.Event()
        async def chunks():
            try:
                yield struct.pack("<h", 12000) * 5760
                await asyncio.sleep(60)
            finally:
                closed.set()
        with tempfile.TemporaryDirectory() as temp:
            player = Path(temp) / "silent-stream-player"
            player.write_text("#!/usr/bin/env python3\nimport sys\nsys.stdin.buffer.read()\n")
            player.chmod(0o700)
            voice = VoiceOutput()
            with patch("argos.voice.shutil.which", return_value=str(player)):
                try:
                    await voice.play_stream(chunks(), started.set)
                    await asyncio.wait_for(started.wait(), 2)
                    child = voice.process
                    self.assertFalse(voice.job.done())
                    self.assertEqual(voice.state, "speaking")
                    self.assertGreater(voice.level, .3)
                    await voice.stop()
                    self.assertTrue(closed.is_set())
                    self.assertIsNotNone(child.returncode)
                    self.assertEqual(voice.state, "idle")
                finally:
                    await voice.stop()

    async def test_stream_reaches_eof_and_reports_player_failure(self):
        async def chunks():
            yield b"\0" * 960
        with tempfile.TemporaryDirectory() as temp:
            player = Path(temp) / "failed-stream-player"
            player.write_text("#!/usr/bin/env python3\nimport sys\nsys.stdin.buffer.read()\nraise SystemExit(7)\n")
            player.chmod(0o700)
            voice = VoiceOutput()
            with patch("argos.voice.shutil.which", return_value=str(player)):
                await voice.play_stream(chunks())
                with self.assertRaises(ArgosError):
                    await voice.job
                self.assertEqual(voice.state, "error")
                await voice.stop()

    async def test_failed_player_is_visible_instead_of_silent_success(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            player = root / "failed-player"
            player.write_text("#!/usr/bin/env python3\nraise SystemExit(7)\n")
            player.chmod(0o700)
            audio = root / "audio.wav"
            with wave.open(str(audio), "wb") as wav:
                wav.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
                wav.writeframes(b"\0" * 3200)
            voice = VoiceOutput()
            with patch("argos.voice.shutil.which", return_value=str(player)):
                await voice.play(audio)
                with self.assertRaises(ArgosError):
                    await voice.job
                self.assertEqual(voice.state, "error")
                self.assertIn("reproductor", voice.last_error)
                await voice.stop()

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
