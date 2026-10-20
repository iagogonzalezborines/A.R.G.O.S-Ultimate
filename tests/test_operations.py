import asyncio
import hashlib
import json
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from argos.core import Core
from argos.linux_tools import files_read, files_write, files_list
from argos.models import ArgosError
from argos.router import Router
from argos.store import Store


class OperationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        self.store = Store(self.root / "state")
        self.record = self.store.add_project("Demo", self.project)
        self.core = Core(self.store)
        await self.core.start()

    async def asyncTearDown(self):
        await self.core.close()
        self.store.close()
        self.temp.cleanup()

    async def req(self, method, **kwargs):
        return await self.core.request({"method": method, "request_id": uuid.uuid4().hex, **kwargs})

    async def settled(self, task_id):
        await asyncio.wait_for(self.core.queue.join(), 5)
        return self.store.task(task_id)

    async def create_write(self, content="hello\n"):
        response = await self.req("run", capability="files.write", project="Demo",
                                  arguments={"file": "demo.txt", "content": content, "expected_sha256": ""})
        return await self.settled(response["task_id"])

    async def test_write_is_prepared_then_exactly_approved(self):
        task = await self.create_write()
        self.assertEqual(task["status"], "WAITING_APPROVAL")
        self.assertFalse((self.project / "demo.txt").exists())
        pending = task["result"]["pending_operation"]
        with self.assertRaises(ArgosError):
            await self.req("approve", task_id=task["id"], fingerprint="wrong")
        await self.req("approve", task_id=task["id"], fingerprint=pending["fingerprint"])
        task = await self.settled(task["id"])
        self.assertEqual(task["status"], "COMPLETED")
        self.assertEqual((self.project / "demo.txt").read_text(), "hello\n")
        with self.assertRaises(ArgosError):
            await self.req("approve", task_id=task["id"], fingerprint=pending["fingerprint"])

    async def test_approval_cannot_cross_task_or_session(self):
        first = await self.create_write()
        second = await self.create_write()
        fingerprint = first["result"]["pending_operation"]["fingerprint"]
        with self.assertRaises(ArgosError):
            await self.req("approve", task_id=second["id"], fingerprint=fingerprint)
        with self.assertRaises(ArgosError):
            await self.req("approve", task_id=first["id"], fingerprint=fingerprint, session="other")
        self.assertFalse((self.project / "demo.txt").exists())

    async def test_file_changed_after_review_is_not_overwritten(self):
        task = await self.create_write()
        (self.project / "demo.txt").write_text("user edit\n")
        await self.req("approve", task_id=task["id"],
                       fingerprint=task["result"]["pending_operation"]["fingerprint"])
        task = await self.settled(task["id"])
        self.assertEqual(task["status"], "FAILED")
        self.assertEqual((self.project / "demo.txt").read_text(), "user edit\n")

    async def test_read_write_hash_and_empty_content(self):
        file = self.project / "plain.txt"
        file.write_text("before")
        file.chmod(0o640)
        read = await files_read(self.record, {"file": "plain.txt"})
        await files_write(self.record, {"file": "plain.txt", "content": "",
                                       "expected_sha256": read["evidence"]["sha256"]})
        self.assertEqual(file.read_bytes(), b"")
        self.assertEqual(file.stat().st_mode & 0o777, 0o640)

    async def test_hidden_and_symlink_files_are_excluded(self):
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "text.txt").write_text("private")
        (self.project / "link").symlink_to(outside, target_is_directory=True)
        (self.project / ".env").write_text("hidden")
        for name in ("../outside/text.txt", ".env", "link/text.txt"):
            with self.assertRaises((ArgosError, OSError)):
                await files_read(self.record, {"file": name})
        listing = await files_list(self.record, {"path": "."})
        self.assertEqual(listing["evidence"], [])

    async def test_failing_registered_command_is_failed_task(self):
        registered = await self.req("commands.register", project="Demo", name="check",
                                    argv=[sys.executable, "-c", "raise SystemExit(7)"])
        response = await self.req("run", capability="commands.run", project="Demo",
                                  arguments=registered["data"])
        task = await self.settled(response["task_id"])
        self.assertEqual(task["status"], "WAITING_APPROVAL")
        pending = task["result"]["pending_operation"]
        self.assertEqual(pending["review"]["argv"][-1], "raise SystemExit(7)")
        await self.req("approve", task_id=task["id"], fingerprint=pending["fingerprint"])
        task = await self.settled(task["id"])
        self.assertEqual(task["status"], "FAILED")
        self.assertEqual(task["result"]["evidence"]["exit_code"], 7)

    async def test_changed_command_definition_is_not_executed(self):
        first = await self.req("commands.register", project="Demo", name="check",
                               argv=[sys.executable, "-c", "print('old')"])
        response = await self.req("run", capability="commands.run", project="Demo", arguments=first["data"])
        task = await self.settled(response["task_id"])
        await self.req("commands.register", project="Demo", name="check",
                       argv=[sys.executable, "-c", "print('new')"])
        await self.req("approve", task_id=task["id"],
                       fingerprint=task["result"]["pending_operation"]["fingerprint"])
        task = await self.settled(task["id"])
        self.assertEqual(task["status"], "FAILED")
        self.assertIn("ha cambiado", task["question"])

    async def test_specialist_resumes_exact_prepared_change_before_model(self):
        observations = []
        class Provider:
            name = "fake-codex"
            async def work(provider, task, context, execute, save_thread, progress):
                observations.append((task["thread_id"], (self.project / "demo.txt").exists()))
                if not task["thread_id"]:
                    save_thread("same-thread")
                    await execute("files.write", {"file": "demo.txt", "content": "approved", "expected_sha256": ""})
                else:
                    self.assertTrue(context["previous_operations"])
                return {"kind": "result", "speech": "Archivo guardado.", "detail": ""}
        self.core.interpreter = Provider()
        response = await self.req("say", text="programacion: crea demo.txt", project="Demo")
        task = await self.settled(response["task_id"])
        await self.req("approve", task_id=task["id"],
                       fingerprint=task["result"]["pending_operation"]["fingerprint"])
        task = await self.settled(task["id"])
        self.assertEqual(task["status"], "COMPLETED")
        self.assertEqual(observations, [(None, False), ("same-thread", True)])
        self.assertEqual(task["result"]["verification"], "changes_not_tested")

    async def test_passed_command_before_edit_does_not_verify_edit(self):
        class Provider:
            name = "fake-codex"
            async def work(provider, task, context, execute, save_thread, progress):
                return {"kind": "result", "speech": "Terminado.", "detail": ""}
        self.core.interpreter = Provider()
        task = self.store.create_task("default", self.record["id"], "engineering", "task")
        self.store.event(task["id"], "CAPABILITY_RESULT",
                         {"capability": "commands.run", "result": {"verification": "command_passed"}})
        self.store.event(task["id"], "CAPABILITY_RESULT",
                         {"capability": "files.write", "result": {"verification": "content_verified"}})
        self.core.queue.put_nowait(task["id"])
        task = await self.settled(task["id"])
        self.assertEqual(task["result"]["verification"], "changes_not_tested")

    def test_local_routes_require_complete_intent(self):
        router = Router()
        self.assertEqual(router.resolve("busca en la web documentación Python").capability, "web.search")
        for text in ("no busca en la web hola", 'dijo "abre Firefox"', "si abro Firefox qué pasa"):
            self.assertEqual(router.resolve(text).kind, "interpret")
        with patch("argos.linux_tools.discover_apps", return_value={
                "firefox": {"id": "firefox", "name": "Firefox", "class": "firefox"}}):
            self.assertEqual(router.resolve("abre Firefox").arguments, {"app": "firefox"})
