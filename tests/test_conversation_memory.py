import tempfile
import unittest
import uuid
from pathlib import Path

from argos.core import Core
from argos.models import Decision
from argos.store import Store


class LocalProvider:
    name = "local-fixture"

    def __init__(self):
        self.history = []

    async def decide(self, text, context):
        self.history = context["recent_conversation"]
        return Decision("answer", speech="Entendido.")


class MemoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_restart_recovers_local_context_without_replaying_tasks(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            store = Store(path)
            core = Core(store, LocalProvider())
            await core.start()
            await core.request({"method": "say", "request_id": uuid.uuid4().hex,
                                "text": "El soporte se llama Helios. Solo estamos hablando."})
            await core.close()
            store.close()
            store = Store(path)
            provider = LocalProvider()
            core = Core(store, provider)
            await core.start()
            try:
                await core.request({"method": "say", "request_id": uuid.uuid4().hex,
                                    "text": "¿Cómo se llama el soporte?"})
                self.assertIn("Helios", provider.history[0]["content"])
                self.assertEqual(store.db.execute("SELECT count(*) FROM conversations").fetchone()[0], 1)
                self.assertEqual(store.tasks(), [])
            finally:
                await core.close()
                store.close()

    def test_resume_is_scoped_and_does_not_import_remote_threads(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Store(Path(temp) / "state")
            project = store.add_project("Demo", temp)
            identifier = store.begin_conversation(None, "one", project["id"], "local", "Hello")
            store.finish_conversation(identifier, "Hi")
            self.assertEqual(store.resumable_conversation("one", project["id"], "local"), identifier)
            self.assertIsNone(store.resumable_conversation("two", project["id"], "local"))
            self.assertIsNone(store.resumable_conversation("one", None, "local"))
            self.assertIsNone(store.resumable_conversation("one", project["id"], "remote"))
            store.finish_conversation(identifier, "", thread_id="remote-thread")
            self.assertIsNone(store.resumable_conversation("one", project["id"], "local"))
            store.close()

    def test_longer_history_keeps_complete_turns_and_excludes_failed_commands(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Store(Path(temp))
            identifier = None
            for index in range(20):
                identifier = store.begin_conversation(identifier, "one", None, "local", f"Question {index}")
                store.finish_conversation(identifier, f"Answer {index}")
            store.begin_conversation(identifier, "one", None, "local", "Do not replay this interrupted command")
            store.finish_conversation(identifier, "Interrupted", "INTERRUPTED")
            history = store.recent_messages(identifier, "one", None)
            self.assertEqual(len(history), 32)
            self.assertEqual(history[0]["content"], "Question 4")
            self.assertEqual(history[-1]["content"], "Answer 19")
            self.assertEqual([m["role"] for m in history], ["user", "assistant"] * 16)
            self.assertEqual(store.recent_messages(identifier, "other", None), [])
            store.begin_conversation(identifier, "one", None, "local", "x" * 15000)
            store.finish_conversation(identifier, "y" * 4000)
            store.begin_conversation(identifier, "one", None, "local", "z" * 15000)
            store.finish_conversation(identifier, "w" * 4000)
            history = store.recent_messages(identifier, "one", None)
            self.assertEqual(len(history), 2)
            self.assertLessEqual(sum(len(m["content"]) for m in history), 24000)
            self.assertEqual(history[0]["content"], "z" * 15000)
            store.close()
