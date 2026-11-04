import asyncio
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from argos.core import Core
from argos.models import ArgosError, Decision, Response, Status
from argos.providers import validate_decision
from argos.store import Store
from argos.wake import WakeListener


class DialogueTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "state")
        self.store.set_setting("voice.language", "en")
        self.core = Core(self.store)
        self.core.speech = SimpleNamespace(language="en", enqueue=Mock(), state="idle", last_error=None)
        self.listener = WakeListener(self.core, None, Path(self.temp.name))
        self.core.wake = self.listener
        await self.core.start()

    async def asyncTearDown(self):
        await self.core.close()
        self.store.close()
        self.temp.cleanup()

    async def req(self, method="say", **kwargs):
        return await self.core.request({"method": method, "request_id": uuid.uuid4().hex, **kwargs})

    def control_audio(self):
        self.core.speech = SimpleNamespace(language="en", automatic_language=True,
            enqueue=Mock(), state="idle", last_error=None, paused=False,
            stop=AsyncMock(), resume_queue=Mock(), job=None)
        self.core.voice = SimpleNamespace(stop=AsyncMock(), state="idle", target=None)
        self.core.capture = SimpleNamespace(cancel=AsyncMock(), toggle=AsyncMock(),
            state="idle", input_device=None, last_error=None)

    async def test_spoken_stop_tears_down_own_listener_without_deadlock_or_late_notifications(self):
        from argos.wake import Utterance
        self.control_audio()
        listener = self.listener
        listener.enabled = listener.dialogue_open = True
        listener.worker = SimpleNamespace(request=AsyncMock(return_value={
            "text": "Stop listening, please.", "language": "en", "language_probability": 1}))
        listener.echo.start = AsyncMock(return_value=False)
        listener.echo.stop = AsyncMock()
        listener._capture_loop = AsyncMock(side_effect=asyncio.Event().wait)
        listener.utterances.put_nowait(Utterance(b"\0" * 640, generation=0))
        self.store.set_setting("voice.wake_enabled", True)
        self.core.deferred_notifications.append(("Old answer", "en", None))
        self.core.approval_dialog.challenges["default"] = {"code": "old"}
        listener.job = asyncio.create_task(listener._run())
        stopped = listener.job
        await asyncio.wait_for(asyncio.gather(stopped, return_exceptions=True), 2)
        await asyncio.wait_for(asyncio.gather(*self.core.voice_controls), 2)
        self.assertFalse(listener.enabled)
        self.assertFalse(listener.dialogue_open)
        self.assertEqual(listener.state, "off")
        self.assertFalse(self.store.setting("voice.wake_enabled"))
        self.assertTrue(self.store.setting("voice.quiet"))
        self.assertNotIn("default", self.core.approval_dialog.challenges)
        await asyncio.wait_for(listener.utterances.join(), 1)
        listener.echo.stop.assert_awaited_once()
        self.core.speech.stop.assert_awaited_once()
        self.core.speech.enqueue.assert_called_once_with("Microphone off.", language="en")
        callback = Mock()
        self.core._speak_notification("Late task result", "en", callback)
        self.core.speech.enqueue.assert_called_once()
        callback.assert_not_called()
        self.assertEqual(self.store.tasks(), [])
        self.assertEqual(list(Path(self.temp.name).glob('wake-*')), [])
        await self.req("voice.toggle")
        self.assertFalse(self.store.setting("voice.quiet"))
        self.core.capture.toggle.assert_awaited_once()

    async def test_manual_stop_cancels_capture_consumer_but_finishes_control(self):
        from argos.speech import Capture
        self.control_audio()
        worker = SimpleNamespace(request=AsyncMock(return_value={
            "text": "Argos, deja de escuchar", "language": "es", "language_probability": 1}))
        capture = Capture(self.core, worker, Path(self.temp.name))
        self.core.capture = capture
        capture.path = str(Path(self.temp.name) / "manual.wav")
        Path(capture.path).write_bytes(b"")
        capture.job = asyncio.create_task(capture._transcribe())
        consumer = capture.job
        await asyncio.wait_for(asyncio.gather(consumer, return_exceptions=True), 2)
        await asyncio.wait_for(asyncio.gather(*self.core.voice_controls), 2)
        self.assertEqual(capture.state, "idle")
        self.assertIsNone(capture.path)
        self.assertTrue(self.store.setting("voice.quiet"))
        self.core.speech.enqueue.assert_called_once_with("Micrófono apagado.", language="es")

    def test_microphone_stop_is_exact_control_not_quoted_negated_or_discussion(self):
        for text in ("Argos, stop listening", "Please stop listening.", "deja de escucharme",
                     "apaga el micrófono", "stop listening to me please"):
            self.assertEqual(self.core.router.resolve(text).kind, "stop_listening", text)
        for text in ('Do not stop listening', 'What does stop listening mean?',
                     '"stop listening"', 'no dejes de escuchar', 'stop listening and delete my files'):
            self.assertNotEqual(self.core.router.resolve(text).kind, "stop_listening", text)

    async def test_stop_talking_is_silent_and_keeps_listener_and_background_task(self):
        self.control_audio()
        self.listener.enabled = self.listener.dialogue_open = True
        task = self.store.create_task("default", None, "computer", "Background",
                                      status=Status.WAITING_INPUT, question="Which screen?")
        await self.listener.handle_transcript({"text": "Argos, stop talking", "language": "en"})
        self.core.speech.stop.assert_awaited_once()
        self.core.speech.enqueue.assert_not_called()
        self.assertTrue(self.listener.enabled)
        self.assertTrue(self.listener.dialogue_open)
        self.assertEqual(self.store.task(task["id"])["status"], "WAITING_INPUT")

    async def test_farewell_with_trailing_name_closes_dialogue_without_shutting_down_wake(self):
        self.listener.enabled = self.listener.dialogue_open = True
        self.core.interpreter = SimpleNamespace(name="test", decide=AsyncMock(return_value=Decision("answer", "Goodbye.")))
        await self.listener.handle_transcript({"text": "That's all, ARGOS.", "language": "en"})
        self.assertFalse(self.listener.dialogue_open)
        self.assertTrue(self.listener.enabled)
        context = self.core.interpreter.decide.call_args.args[1]
        self.assertTrue(context["interaction"]["ending_dialogue"])
        calls = self.core.interpreter.decide.await_count
        await self.listener.handle_transcript({"text": "Background conversation"})
        self.assertEqual(self.core.interpreter.decide.await_count, calls)

    async def test_engineering_keeps_full_report_in_monitor_and_only_speaks_summary(self):
        path = Path(self.temp.name) / "fixture.py"
        path.write_text("value = 1\n")
        summary = "I inspected the fixture. No changes or tests were made."
        detail = "Read-only findings.\n" + "Technical detail preserved.\n" * 80
        class Provider:
            name = "test"
            async def work(provider, task, context, execute, save_thread, progress):
                await execute("files.read", {"file": str(path)})
                return {"kind": "result", "speech": summary, "detail": detail}
        self.core.interpreter = Provider()
        result = self.core._decision(Decision("delegate", agent="engineering"), "Inspect fixture", None, "default")
        self.store.set_setting("task.language:" + result.task_id, "en")
        await asyncio.wait_for(self.core.queue.join(), 2)
        task = self.store.task(result.task_id)
        self.assertEqual(task["result"]["verification"], "inspection_only")
        self.assertEqual(task["result"]["detail"], detail)
        self.core.speech.enqueue.assert_called_once_with(summary, language="en")
        from argos.telemetry import detail as monitor_detail
        display = monitor_detail(self.core, {"id": result.task_id, "session": "default"})
        self.assertIn(detail, "\n".join(m["content"] for m in display["messages"]))

    async def test_new_input_suppresses_late_reply_but_keeps_history_and_latest_answer(self):
        entered, release = asyncio.Event(), asyncio.Event()

        class Provider:
            name = "test"

            async def decide(provider, text, context):
                if text == "First question":
                    entered.set()
                    await release.wait()
                return Decision("answer", speech="Answer to " + text)

        self.core.interpreter = Provider()
        old = asyncio.create_task(self.req(text="First question", speak=True, conversation=True,
                                           voice_generation=0))
        await entered.wait()
        self.listener.input_generation = 1
        release.set()
        result = await old
        self.assertEqual(result["speech"], "Answer to First question")
        self.core.speech.enqueue.assert_not_called()
        self.assertEqual(self.listener.diagnostics["suppressed_replies"], 1)
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM messages").fetchone()[0], 2)
        await self.req(text="My correction", speak=True, conversation=True, voice_generation=1)
        self.core.speech.enqueue.assert_called_once_with("Answer to My correction", language="en")

    async def test_unheard_superseded_plan_never_enables_spoken_approval(self):
        development = SimpleNamespace(present=Mock())
        self.listener.input_generation = 2
        with patch.object(self.core, "development", development), patch.object(
                self.core, "_dispatch", AsyncMock(return_value=Response("Plan", "plan_review", "task-id"))):
            await self.req(text="plan", speak=True, conversation=True, voice_generation=1)
        development.present.assert_not_called()
        self.core.speech.enqueue.assert_not_called()

    async def test_slow_inference_and_new_speech_only_play_latest_complete_answer(self):
        from argos.speech import Speech
        entered, release = asyncio.Event(), asyncio.Event()
        spoken = []

        class Provider:
            name = "test"

            async def decide(provider, text, context):
                if text == "First question":
                    entered.set()
                    await release.wait()
                return Decision("answer", speech="Answer to " + text)

        async def chunks(text, language):
            spoken.append(text)
            yield b"\0\0"

        async def play(chunks, first_audio):
            async for _ in chunks:
                first_audio()

        self.core.interpreter = Provider()
        self.core.speech = Speech(SimpleNamespace(chunks=chunks),
                                  SimpleNamespace(play_stream=play, job=None), Path(self.temp.name))
        self.listener.worker = SimpleNamespace(request=AsyncMock(side_effect=[
            {"text": "Argos, First question", "language": "en", "language_probability": 1},
            {"text": "My correction", "language": "en", "language_probability": 1}]))
        old = asyncio.create_task(self.listener.process_audio(b"\0" * 3200, generation=0))
        await entered.wait()
        self.listener.input_generation = 1
        self.listener.collecting_input = True
        release.set()
        await old
        self.assertTrue(self.core.speech.paused)
        self.assertEqual(spoken, [])
        self.listener.collecting_input = False
        await self.listener.process_audio(b"\0" * 3200, interrupted=True, generation=1)
        await self.core.speech.job
        self.assertEqual(spoken, ["Answer to My correction"])
        await asyncio.wait_for(self.core.speech.queue.join(), 1)

    async def test_model_acknowledgement_proposal_yes_are_spoken_unchanged_once_per_turn(self):
        observed = []
        class Provider:
            name = "stateless-test"
            async def decide(provider, text, context, agent="general"):
                observed.append((text, context["recent_conversation"]))
                if text == "are you there?":
                    self.assertEqual(context["interaction"]["channel"], "voice")
                    return Decision("answer", "I'm here. What do you need?")
                if text == "Yes":
                    self.assertEqual(context["recent_conversation"][-1]["content"],
                                     "May I explain a printable bracket solution?")
                    return Decision("answer", "A removable bracket could organize the components.")
                return Decision("answer", "May I explain a printable bracket solution?")
        self.core.interpreter = Provider()
        await self.listener.handle_transcript({"text": "Argos?"})
        self.assertEqual(observed, [])
        self.core.speech.enqueue.assert_not_called()
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 0)
        await self.listener.handle_transcript({"text": "are you there?"})
        self.core.speech.enqueue.assert_called_once_with("I'm here. What do you need?", language="en")
        self.assertEqual(len(observed), 1)
        await self.listener.handle_transcript({"text": "I need you to check this out on my setup"})
        await self.listener.handle_transcript({"text": "Yes"})
        self.assertEqual(len(observed), 3)
        self.assertEqual([call.args[0] for call in self.core.speech.enqueue.call_args_list], [
            "I'm here. What do you need?", "May I explain a printable bracket solution?",
            "A removable bracket could organize the components."])
        self.assertTrue(self.listener.dialogue_open)
        self.assertFalse(self.store.tasks())
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM conversations").fetchone()[0], 1)
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 6)

    async def test_presence_check_and_greeting_use_model_words_without_fixed_honorific(self):
        responses = iter(("Yes?", "Hello. What's on your mind?", "Here, sir."))
        inputs = []
        class Provider:
            name = "test"
            async def decide(provider, text, context, agent="general"):
                inputs.append(text)
                return Decision("answer", next(responses))
        self.core.interpreter = Provider()
        for text in ("Argos, are you there?", "hello", "Argos?"):
            await self.listener.handle_transcript({"text": text})
        self.assertEqual(inputs, ["are you there?", "hello"])
        self.assertEqual([call.args[0] for call in self.core.speech.enqueue.call_args_list],
                         ["Yes?", "Hello. What's on your mind?"])

    async def test_split_wake_name_then_question_makes_only_one_provider_request(self):
        inputs = []
        class Provider:
            name = "test"
            async def decide(provider, text, context, agent="general"):
                inputs.append(text)
                if text in ("ARGOS.", "Argos?"):
                    raise ArgosError("NVIDIA tarda demasiado. Inténtalo de nuevo.")
                return Decision("answer", "Yes, I can hear you.")
        self.core.interpreter = Provider()
        for text in ("ARGOS.", "Argos?", "Hello, can you hear me?"):
            await self.listener.handle_transcript({"text": text, "language": "en"})
        self.assertEqual(inputs, ["Hello, can you hear me?"])
        self.core.speech.enqueue.assert_called_once_with("Yes, I can hear you.", language="en")
        self.assertEqual(self.listener.diagnostics["activation_only"], 2)
        self.assertEqual(self.listener.diagnostics["completed_turns"], 1)
        self.assertIsNone(self.listener.last_error)
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 2)
        self.assertEqual(self.store.tasks(), [])

    async def test_interrupted_reply_context_preserves_tasks_and_actual_model_response(self):
        observed = []
        class Provider:
            name = "test"
            async def decide(provider, text, context, agent="general"):
                observed.append((text, context["interaction"]["speech_interrupted"]))
                return Decision("answer", "The smaller bracket, understood.")
        self.core.interpreter = Provider()
        task = self.store.create_task("default", None, "computer", "Independent work")
        before = self.store.task(task["id"])
        await self.listener.handle_transcript({"text": "Argos, I meant the smaller one"}, interrupted=True)
        self.core.speech.enqueue.assert_called_once_with("The smaller bracket, understood.", language="en")
        await self.listener.handle_transcript({"text": "What material?"})
        self.assertEqual(observed, [("I meant the smaller one", True), ("What material?", False)])
        self.assertEqual(self.store.task(task["id"]), before)

    async def test_voice_status_exposes_barge_in_readiness_and_loss_without_database_writes(self):
        self.listener.enabled = self.listener.echo.active = True
        self.listener.interruptions = 2
        before = self.store.db.total_changes
        response = await self.req("voice.state")
        self.assertTrue(response["data"]["barge_in_available"])
        self.assertEqual(response["data"]["voice_interruptions"], 2)
        self.listener.enabled = self.listener.echo.active = False
        self.listener.last_error = "Lost echo cancellation"
        response = await self.req("voice.state")
        self.assertFalse(response["data"]["barge_in_available"])
        self.assertEqual(response["data"]["state"], "error")
        self.assertEqual(self.store.db.total_changes, before)

    async def test_recent_conversation_is_scoped_to_session_and_project(self):
        observed = []
        class Provider:
            name = "test"
            async def decide(provider, text, context, agent="general"):
                observed.append(context["recent_conversation"])
                return Decision("answer", "A proposal for this conversation.")
        self.core.interpreter = Provider()
        path = Path(self.temp.name) / "project"
        path.mkdir()
        self.store.add_project("Demo", path)
        await self.req(text="Could you explain my options?")
        await self.req(text="Yes", session="other")
        await self.req(text="Yes", project="Demo")
        self.assertEqual(observed, [[], [], []])

    async def test_natural_reply_returns_original_words_to_same_task(self):
        questions = []
        class Provider:
            name = "test"
            async def decide(provider, text, context, agent="general"):
                questions.extend(context["pending_questions"])
                return Decision("reply", arguments={"task_id": context["pending_questions"][0]["task_id"]})
            async def work(provider, task, context, execute, save_thread, progress):
                self.assertEqual(context["task"]["answers"], ["Yes, use the existing measurements"])
                self.assertEqual(task["thread_id"], "existing-task-thread")
                await execute("system.info", {})
                return {"kind": "result", "speech": "System inspected.", "detail": ""}
        self.core.interpreter = Provider()
        task = self.store.create_task("default", None, "computer", "Inspect setup")
        self.core.task_provider(task)
        self.store.update(task["id"], Status.RUNNING, thread_id="existing-task-thread")
        self.store.update(task["id"], Status.WAITING_INPUT, question="Use the existing measurements?")
        response = await self.req(text="Yes, use the existing measurements")
        self.assertEqual(response["task_id"], task["id"])
        await asyncio.wait_for(self.core.queue.join(), 5)
        self.assertEqual(self.store.task(task["id"])["status"], "COMPLETED")
        self.assertEqual(len(self.store.tasks()), 1)
        self.assertEqual(questions[0]["question"], "Use the existing measurements?")

    async def test_reply_cannot_target_other_session_or_approval(self):
        class Provider:
            name = "test"
            async def decide(provider, text, context, agent="general"):
                return Decision("reply", arguments={"task_id": target["id"]})
        self.core.interpreter = Provider()
        target = self.store.create_task("other", None, "computer", "task", status=Status.WAITING_INPUT,
                                        question="Continue?")
        with self.assertRaises(ArgosError):
            await self.req(text="Yes")
        target = self.store.create_task("default", None, "computer", "task")
        self.store.update(target["id"], Status.RUNNING)
        self.store.update(target["id"], Status.WAITING_APPROVAL, question="Approve?")
        with self.assertRaises(ArgosError):
            await self.req(text="Yes")
        self.assertEqual(self.store.task(target["id"])["status"], "WAITING_APPROVAL")

    async def test_farewell_keeps_tasks_and_invalidates_old_approval_challenge(self):
        task = self.store.create_task("default", None, "computer", "background", status=Status.WAITING_INPUT,
                                      question="Which screen?")
        self.core.approval_dialog.challenges["default"] = {"code": "old"}
        self.listener.dialogue_open = True
        await self.listener.handle_transcript({"text": "that's all"})
        self.assertFalse(self.listener.dialogue_open)
        self.assertNotIn("default", self.core.approval_dialog.challenges)
        self.assertEqual(self.store.task(task["id"])["status"], "WAITING_INPUT")

    def test_reply_schema_cannot_inject_answer_or_specialist_authority(self):
        data = {"kind": "reply", "speech": "", "agent": "", "capability": "",
                "arguments": {"task_id": "a" * 32}}
        self.assertEqual(validate_decision(data).kind, "reply")
        with self.assertRaises(ArgosError):
            validate_decision(data, "engineering")
        with self.assertRaises(ArgosError):
            validate_decision({**data, "arguments": {"task_id": "a" * 32, "text": "invented authorization"}})
