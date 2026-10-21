import asyncio
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from argos.core import Core
from argos.models import ArgosError, Decision, Status
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

    async def test_model_acknowledgement_proposal_yes_are_spoken_unchanged_once_per_turn(self):
        observed = []
        class Provider:
            name = "stateless-test"
            async def decide(provider, text, context, agent="general"):
                observed.append((text, context["recent_conversation"]))
                if text == "Argos?":
                    self.assertEqual(context["interaction"]["channel"], "voice")
                    return Decision("answer", "I'm here. What do you need?")
                if text == "Yes":
                    self.assertEqual(context["recent_conversation"][-1]["content"],
                                     "May I explain a printable bracket solution?")
                    return Decision("answer", "A removable bracket could organize the components.")
                return Decision("answer", "May I explain a printable bracket solution?")
        self.core.interpreter = Provider()
        await self.listener.handle_transcript({"text": "Argos?"})
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
        self.assertEqual(inputs, ["are you there?", "hello", "Argos?"])
        self.assertEqual([call.args[0] for call in self.core.speech.enqueue.call_args_list],
                         ["Yes?", "Hello. What's on your mind?", "Here, sir."])

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
