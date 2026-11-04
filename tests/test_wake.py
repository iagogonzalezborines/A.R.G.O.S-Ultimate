import asyncio
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from argos.models import ArgosError
from argos.router import Router
from argos.wake import Endpoint, Utterance, WakeListener


class WakeTests(unittest.IsolatedAsyncioTestCase):
    def listener(self, directory):
        core = SimpleNamespace(request=AsyncMock(), capture=SimpleNamespace(state="idle", input_device=None),
                               voice=SimpleNamespace(state="idle"),
                               speech=SimpleNamespace(state="idle", paused=False, automatic_language=True,
                                                      language="es", resume_queue=lambda: None, enqueue=Mock()))
        worker = SimpleNamespace(request=AsyncMock(return_value={"text": "Argos, hola", "language": "es"}))
        return WakeListener(core, worker, Path(directory))

    def test_endpoint_silence_preroll_and_maximum_duration(self):
        detector = Endpoint()
        silence = b"\0" * 640
        voice = struct.pack("<320h", *([1500] * 320))
        for _ in range(100):
            self.assertIsNone(detector.feed(silence))
        for _ in range(20):
            self.assertIsNone(detector.feed(voice))
        result = None
        for _ in range(40):
            result = detector.feed(silence)
        self.assertTrue(result.startswith(silence))
        self.assertIn(voice, result)
        self.assertEqual(detector.frames, [])
        for _ in range(999):
            self.assertIsNone(detector.feed(voice))
        self.assertIsNotNone(detector.feed(voice))

    async def test_wake_gate_ignores_ambient_quoted_negated_and_embedded_mentions(self):
        with tempfile.TemporaryDirectory() as temp:
            listener = self.listener(temp)
            for text in ("hola", "no Argos abre algo", 'dijo "Argos, abre algo"', "hablamos de Argos", '"Argos abre Firefox"'):
                await listener.handle_transcript({"text": text})
            listener.core.request.assert_not_called()
            listener.session = "office"
            await listener.handle_transcript({"text": "Argos, abre Firefox", "language": "es"})
            request = listener.core.request.call_args.args[0]
            self.assertEqual(request["text"], "abre Firefox")
            self.assertEqual(request["session"], "office")

    async def test_diagnostics_distinguish_empty_unmatched_and_accepted_without_text(self):
        with tempfile.TemporaryDirectory() as temp:
            listener = self.listener(temp)
            await listener.handle_transcript({"text": "   "})
            self.assertEqual(listener.diagnostics["last_result"], "empty_transcript")
            await listener.handle_transcript({"text": "private ambient words"})
            self.assertEqual(listener.diagnostics["last_result"], "invocation_not_recognized")
            listener.core.request.assert_not_called()
            await listener.handle_transcript({"text": "Argos, hello"})
            self.assertEqual(listener.diagnostics["last_result"], "accepted")
            self.assertEqual(listener.diagnostics["empty_transcripts"], 1)
            self.assertEqual(listener.diagnostics["unmatched_invocations"], 1)
            self.assertEqual(listener.diagnostics["accepted_turns"], 1)
            self.assertNotIn("private", str(listener.diagnostics))
            self.assertNotIn("hello", str(listener.diagnostics))
            self.assertEqual(list(Path(temp).iterdir()), [])

    async def test_invocation_opens_locally_and_keeps_multiple_turns_without_deadline(self):
        with tempfile.TemporaryDirectory() as temp:
            listener = self.listener(temp)
            await listener.handle_transcript({"text": "Argos?"})
            self.assertTrue(listener.dialogue_open)
            listener.core.request.assert_not_called()
            self.assertEqual(listener.diagnostics["activation_only"], 1)
            self.assertEqual(listener.diagnostics["accepted_turns"], 0)
            for now, text in ((100, "I need you to check this out on my setup"),
                              (10000, "Yes"), (100000, "What about the other option?")):
                with patch("time.monotonic", return_value=now):
                    await listener.handle_transcript({"text": text})
                self.assertEqual(listener.core.request.call_args.args[0]["text"], text)
                self.assertTrue(listener.dialogue_open)
            self.assertEqual(listener.core.request.call_count, 3)

    async def test_explicit_farewell_returns_to_standby_without_disabling_listener(self):
        with tempfile.TemporaryDirectory() as temp:
            listener = self.listener(temp)
            listener.enabled = True
            await listener.handle_transcript({"text": "Argos, hello"})
            await listener.handle_transcript({"text": "that's all"})
            self.assertFalse(listener.dialogue_open)
            self.assertTrue(listener.enabled)
            self.assertTrue(listener.core.request.call_args.args[0]["end_dialogue"])
            count = listener.core.request.call_count
            await listener.handle_transcript({"text": "background conversation"})
            self.assertEqual(listener.core.request.call_count, count)
            await listener.handle_transcript({"text": "¿Argos?"})
            self.assertTrue(listener.dialogue_open)
            self.assertEqual(listener.core.request.call_count, count)

    async def test_stop_closes_dialogue_and_drops_buffered_audio(self):
        with tempfile.TemporaryDirectory() as temp:
            listener = self.listener(temp)
            listener.dialogue_open = True
            listener.utterances.put_nowait(Utterance(b"pending"))
            await listener.stop()
            self.assertFalse(listener.dialogue_open)
            self.assertTrue(listener.utterances.empty())
            self.assertEqual(listener.state, "off")

    async def test_audio_is_private_temporary_and_never_forwarded(self):
        with tempfile.TemporaryDirectory() as temp:
            listener = self.listener(temp)
            await listener.process_audio(b"\0" * 3200)
            self.assertEqual(list(Path(temp).iterdir()), [])
            self.assertFalse(listener.core.speech.paused)
            request = listener.core.request.call_args.args[0]
            self.assertNotIn("path", request)
            self.assertNotIn("audio", request)
            self.assertEqual(request["text"], "hola")

    async def test_cancel_during_stt_removes_capture_and_resumes_notifications(self):
        with tempfile.TemporaryDirectory() as temp:
            listener = self.listener(temp)
            entered = asyncio.Event()
            async def recognize(message):
                entered.set()
                await asyncio.Event().wait()
            listener.worker.request = recognize
            task = asyncio.create_task(listener.process_audio(b"\0" * 3200))
            await entered.wait()
            self.assertEqual(len(list(Path(temp).iterdir())), 1)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            self.assertEqual(list(Path(temp).iterdir()), [])
            self.assertFalse(listener.core.speech.paused)
            self.assertFalse(listener.busy)

    async def test_disabled_listener_never_opens_microphone(self):
        with tempfile.TemporaryDirectory() as temp:
            listener = self.listener(temp)
            with patch("asyncio.create_subprocess_exec", AsyncMock()) as spawn:
                await listener.configure(False)
                await asyncio.sleep(0)
                spawn.assert_not_called()
            self.assertFalse(listener.enabled)

    async def test_speaking_or_manual_capture_pauses_listener(self):
        with tempfile.TemporaryDirectory() as temp:
            listener = self.listener(temp)
            self.assertTrue(listener.available())
            listener.core.voice.state = "speaking"
            self.assertFalse(listener.available())
            listener.core.voice.state = "idle"
            listener.core.capture.state = "listening"
            self.assertFalse(listener.available())

    async def test_missing_device_does_not_open_default_microphone(self):
        with tempfile.TemporaryDirectory() as temp:
            listener = self.listener(temp)
            listener.core.capture.input_device = "missing"
            with patch("argos.speech.input_devices", AsyncMock(return_value=[])), \
                 patch("asyncio.create_subprocess_exec", AsyncMock()) as spawn:
                with self.assertRaises(ArgosError):
                    await listener._capture_loop()
                spawn.assert_not_called()

    async def test_barge_in_stops_speech_before_endpoint_and_keeps_preroll_while_stop_is_slow(self):
        with tempfile.TemporaryDirectory() as temp:
            listener = self.listener(temp)
            listener.enabled = listener.dialogue_open = listener.echo.active = True
            listener.core.voice.state = "speaking"
            stopped, release = asyncio.Event(), asyncio.Event()
            async def interrupt():
                stopped.set()
                await release.wait()  # Reaping synthesis cannot block capture.
                listener.core.voice.state = "idle"
            listener.core.speech.interrupt = AsyncMock(side_effect=interrupt)
            silence = b"\0" * 640
            voice = struct.pack("<320h", *([1500] * 320))
            frames = [silence] * 10 + [voice] * 20 + [silence] * 40
            index = 0
            async def read(count):
                nonlocal index
                await asyncio.sleep(0)
                if index == 18:
                    self.assertTrue(stopped.is_set())
                    self.assertTrue(listener.utterances.empty())
                frame = frames[index]
                index += 1
                if index == len(frames):
                    listener.enabled = False
                return frame
            child = SimpleNamespace(stdout=SimpleNamespace(readexactly=read))
            with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=child)) as spawn:
                await listener._capture_loop()
            self.assertIn(listener.echo.source, spawn.call_args.args)
            self.assertTrue(listener.core.speech.paused)
            self.assertTrue(listener.dialogue_open)
            self.assertEqual(listener.interruptions, 1)
            listener.core.speech.interrupt.assert_awaited_once()
            utterance = listener.utterances.get_nowait()
            self.assertTrue(utterance.interrupted)
            self.assertEqual(utterance.pcm, silence * 9 + voice * 20 + silence * 40)
            release.set()
            await listener.interrupt_job
            await listener.process_audio(utterance.pcm, interrupted=utterance.interrupted)
            self.assertTrue(listener.core.request.call_args.args[0]["speech_interrupted"])
            self.assertFalse(listener.core.speech.paused)
            self.assertEqual(list(Path(temp).iterdir()), [])

    async def test_post_aec_silence_and_isolated_clicks_do_not_interrupt(self):
        with tempfile.TemporaryDirectory() as temp:
            listener = self.listener(temp)
            listener.enabled = listener.dialogue_open = listener.echo.active = True
            listener.core.voice.state = "speaking"
            listener.core.speech.interrupt = AsyncMock()
            silence, click = b"\0" * 640, struct.pack("<320h", *([2000] * 320))
            frames = [silence] * 50 + [click] + [silence] * 50
            async def read(count):
                frame = frames.pop(0)
                listener.enabled = bool(frames)
                return frame
            with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=SimpleNamespace(
                    stdout=SimpleNamespace(readexactly=read)))):
                await listener._capture_loop()
            listener.core.speech.interrupt.assert_not_called()
            self.assertTrue(listener.utterances.empty())

    async def test_cancelled_playback_does_not_cancel_waiting_turn_consumer(self):
        with tempfile.TemporaryDirectory() as temp:
            listener = self.listener(temp)
            listener.enabled = listener.dialogue_open = True
            listener.utterances.put_nowait(Utterance(b"correction", True))
            speech = asyncio.create_task(asyncio.Event().wait())
            listener.core.speech.job = speech
            observed = []
            async def process_audio(pcm, interrupted=False, generation=None):
                observed.append((pcm, interrupted))
                listener.enabled = False
            listener.process_audio = process_audio
            consumer = asyncio.create_task(listener._turn_loop())
            await asyncio.sleep(0)
            speech.cancel()
            await asyncio.wait_for(consumer, 1)
            self.assertEqual(observed, [(b"correction", True)])
            self.assertTrue(listener.dialogue_open)

    async def test_aec_failure_stops_listener_and_releases_playback_route(self):
        with tempfile.TemporaryDirectory() as temp:
            listener = self.listener(temp)
            listener.enabled = listener.dialogue_open = True
            listener.core.speech.stop = AsyncMock()
            listener.echo.start = AsyncMock(return_value=True)
            listener.echo.stop = AsyncMock()
            listener.echo.watch = AsyncMock(side_effect=ArgosError("lost AEC"))
            listener._capture_loop = AsyncMock(side_effect=lambda: None)
            await listener._run()
            self.assertFalse(listener.enabled)
            self.assertFalse(listener.dialogue_open)
            self.assertEqual(listener.state, "error")
            self.assertIsNone(listener.core.voice.target)
            listener.core.speech.stop.assert_awaited_once()
            listener.echo.stop.assert_awaited_once()

    async def test_aec_unavailable_keeps_conversation_with_barge_in_disabled(self):
        with tempfile.TemporaryDirectory() as temp:
            listener = self.listener(temp)
            listener.enabled = True
            listener.echo.start = AsyncMock(return_value=False)
            listener.echo.stop = AsyncMock()
            async def capture():
                self.assertFalse(listener.echo.active)
                listener.enabled = False
            listener._capture_loop = capture
            await listener._run()
            listener.echo.stop.assert_awaited_once()

    async def test_continuous_capture_drains_playback_without_restarting_and_queues_followups(self):
        with tempfile.TemporaryDirectory() as temp:
            listener = self.listener(temp)
            listener.enabled = True
            silent = b"\0" * 640
            voiced = struct.pack("<320h", *([1500] * 320))
            # Three phrases: the middle one is ARGOS playback and must vanish.
            frames = [(voiced, False)] * 20 + [(silent, False)] * 40
            frames += [(voiced, True)] * 20 + [(silent, True)] * 40
            frames += [(voiced, False)] * 20 + [(silent, False)] * 40
            index = 0
            async def readexactly(count):
                nonlocal index
                frame, speaking = frames[index]
                listener.core.voice.state = "speaking" if speaking else "idle"
                index += 1
                if index == len(frames):
                    listener.enabled = False
                return frame
            process = SimpleNamespace(stdout=SimpleNamespace(readexactly=readexactly))
            # Recognition/inference can be busy without dropping the next turn.
            listener.busy = True
            listener.core.speech.paused = True
            with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=process)) as spawn:
                await listener._capture_loop()
                spawn.assert_awaited_once()
            self.assertEqual(listener.utterances.qsize(), 2)
            first, second = listener.utterances.get_nowait(), listener.utterances.get_nowait()
            self.assertEqual(first.pcm, second.pcm)
            self.assertLess(first.generation, second.generation)

    async def test_turn_error_does_not_close_conversation(self):
        with tempfile.TemporaryDirectory() as temp:
            listener = self.listener(temp)
            listener.enabled = listener.dialogue_open = True
            listener.utterances.put_nowait(Utterance(b"first"))
            listener.utterances.put_nowait(Utterance(b"second"))
            observed = []
            async def process_audio(pcm, interrupted=False, generation=None):
                observed.append(pcm)
                if pcm == b"first":
                    raise ArgosError("Wrong approval code")
                listener.enabled = False
            listener.process_audio = process_audio
            await listener._turn_loop()
            self.assertEqual(observed, [b"first", b"second"])
            self.assertTrue(listener.dialogue_open)
            listener.core.speech.enqueue.assert_not_called()

    async def test_stale_error_does_not_interrupt_queued_input_and_recovers(self):
        from argos.speech import Speech
        with tempfile.TemporaryDirectory() as temp:
            listener = self.listener(temp)
            listener.enabled = True
            spoken = []
            async def chunks(text, language):
                spoken.append((text, language))
                yield b"\0\0"
            async def play(chunks, first_audio):
                async for _ in chunks:
                    first_audio()
            worker = SimpleNamespace(chunks=chunks)
            output = SimpleNamespace(play_stream=play, job=None)
            listener.core.speech = Speech(worker, output, Path(temp))
            listener.core.speech.language = "en"
            listener.utterances.put_nowait(Utterance(b"\0" * 3200))
            listener.utterances.put_nowait(Utterance(b"\0" * 3200))
            observed = []
            async def request(message):
                observed.append(message)
                if len(observed) == 1:
                    raise ArgosError("NVIDIA tarda demasiado. Inténtalo de nuevo.")
                self.assertEqual(spoken, [])
                self.assertIn("dispatch_ms", first_timings)
                listener.enabled = False
            listener.core.request = request
            first_timings = {}
            original_process = listener.process_audio
            async def process_audio(*args, **kwargs):
                try:
                    return await original_process(*args, **kwargs)
                finally:
                    if not first_timings:
                        first_timings.update(listener.timings)
            listener.process_audio = process_audio
            await asyncio.wait_for(listener._turn_loop(), 1)
            self.assertEqual(len(observed), 2)
            self.assertEqual(listener.diagnostics["failed_turns"], 1)
            self.assertEqual(listener.diagnostics["completed_turns"], 1)
            self.assertIsNone(listener.last_error)
            self.assertTrue(listener.dialogue_open)
            self.assertEqual(list(Path(temp).iterdir()), [])

    async def test_new_speech_during_inference_claims_floor_without_playback(self):
        with tempfile.TemporaryDirectory() as temp:
            listener = self.listener(temp)
            listener.enabled = listener.dialogue_open = listener.echo.active = listener.busy = True
            listener.core.speech.interrupt = AsyncMock()
            voice = struct.pack("<320h", *([1500] * 320))
            frames = [voice] * 20 + [b"\0" * 640] * 40

            async def read(count):
                await asyncio.sleep(0)
                if len(frames) == 52:
                    self.assertTrue(listener.collecting_input)
                    self.assertTrue(listener.core.speech.paused)
                    self.assertFalse(listener.input_idle.is_set())
                    self.assertEqual(listener.input_generation, 1)
                frame = frames.pop(0)
                listener.enabled = bool(frames)
                return frame

            child = SimpleNamespace(stdout=SimpleNamespace(readexactly=read))
            with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=child)):
                await listener._capture_loop()
            await listener.interrupt_job
            self.assertEqual(listener.utterances.get_nowait().generation, 1)
            self.assertTrue(listener.input_idle.is_set())
            listener.core.speech.interrupt.assert_awaited_once()

    async def test_previous_inference_finishing_cannot_resume_while_user_speaks(self):
        with tempfile.TemporaryDirectory() as temp:
            listener = self.listener(temp)
            listener.collecting_input = True
            await listener.process_audio(b"\0" * 3200, generation=0)
            self.assertTrue(listener.core.speech.paused)
            self.assertFalse(listener.busy)

    async def test_buffered_fragments_wait_for_user_and_reach_one_turn_in_order(self):
        with tempfile.TemporaryDirectory() as temp:
            listener = self.listener(temp)
            listener.enabled = listener.dialogue_open = True
            listener.input_idle.clear()
            listener.utterances.put_nowait(Utterance(b"first", False, 1))
            observed = []

            async def process_audio(pcm, interrupted=False, generation=None):
                observed.append((pcm, interrupted, generation))
                listener.enabled = False

            listener.process_audio = process_audio
            consumer = asyncio.create_task(listener._turn_loop())
            await asyncio.sleep(0)
            self.assertEqual(observed, [])
            listener.utterances.put_nowait(Utterance(b"second", True, 2))
            listener.utterances.put_nowait(Utterance(b"third", False, 3))
            listener.input_idle.set()
            await asyncio.wait_for(consumer, 1)
            self.assertEqual(observed, [(b"firstsecondthird", True, 3)])
            self.assertEqual(listener.diagnostics["merged_segments"], 2)
            await asyncio.wait_for(listener.utterances.join(), 1)

    async def test_current_error_without_new_input_is_still_spoken(self):
        with tempfile.TemporaryDirectory() as temp:
            listener = self.listener(temp)
            listener.enabled = True
            listener.input_generation = 3
            listener.utterances.put_nowait(Utterance(b"input", generation=3))

            async def fail(*args, **kwargs):
                listener.enabled = False
                raise ArgosError("Current failure")

            listener.process_audio = fail
            await listener._turn_loop()
            listener.core.speech.enqueue.assert_called_once_with("Current failure", language="es")

    async def test_full_input_queue_keeps_latest_correction_and_balances_join(self):
        with tempfile.TemporaryDirectory() as temp:
            listener = self.listener(temp)
            listener.enabled = True
            for i in range(4):
                listener.utterances.put_nowait(Utterance(bytes([i]), generation=i))
            listener.input_generation = 3
            voice = struct.pack("<320h", *([1500] * 320))
            frames = [voice] * 20 + [b"\0" * 640] * 40

            async def read(count):
                frame = frames.pop(0)
                listener.enabled = bool(frames)
                return frame

            child = SimpleNamespace(stdout=SimpleNamespace(readexactly=read))
            with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=child)):
                await listener._capture_loop()
            queued = []
            while not listener.utterances.empty():
                queued.append(listener.utterances.get_nowait())
                listener.utterances.task_done()
            self.assertEqual([u.generation for u in queued], [1, 2, 3, 4])
            self.assertIn(voice, queued[-1].pcm)
            self.assertEqual(listener.diagnostics["discarded_segments"], 1)
            await asyncio.wait_for(listener.utterances.join(), 1)

    def test_approval_phrases_are_exact_and_not_model_decisions(self):
        router = Router()
        for phrase in ('no aprueba luna pino', 'dijo "aprueba luna pino"', 'si digo aprueba luna pino'):
            self.assertNotEqual(router.resolve(phrase).kind, "approval_confirm")
        self.assertEqual(router.resolve("Argos, aprueba luna pino cobre faro").kind, "approval_confirm")
        self.assertEqual(router.resolve("Argos, aprueba: luna, pino, cobre, faro.").arguments["code"],
                         "luna pino cobre faro")
