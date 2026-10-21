import asyncio
import hashlib
import json
import sys
import tempfile
import threading
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from argos import filesystem as fs
from argos.core import Core
from argos.models import ArgosError
from argos.store import Store


class HostFilesTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root / "state")
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

    async def operation(self, name, arguments):
        response = await self.req("run", capability=name, arguments=arguments)
        return await self.settled(response["task_id"])

    async def approve(self, task):
        await self.req("approve", task_id=task["id"],
                       fingerprint=task["result"]["pending_operation"]["fingerprint"])
        return await self.settled(task["id"])

    async def test_absolute_read_large_unicode_and_versioned_pages(self):
        path = self.root / "large.txt"
        content = "árbol 🌲\n" * 20000
        path.write_text(content)
        result = await fs.files_read(None, {"file": str(path)})
        chunks = [result["evidence"]["content"]]
        digest = result["evidence"]["sha256"]
        while result["evidence"]["next_offset"]:
            result = await fs.files_read(None, {"file": str(path), "offset": result["evidence"]["next_offset"],
                                                "limit": "32000", "expected_sha256": digest})
            chunks.append(result["evidence"]["content"])
        self.assertEqual("".join(chunks), content)
        self.assertEqual(digest, hashlib.sha256(path.read_bytes()).hexdigest())
        path.write_text("changed")
        with self.assertRaises(ArgosError):
            await fs.files_read(None, {"file": str(path), "offset": "0", "limit": "100", "expected_sha256": digest})

    async def test_large_patch_preserves_remainder_and_checks_version(self):
        path = self.root / "large.txt"
        content = "á" * 80000 + "old" + "fin" * 30000
        path.write_text(content)
        digest = fs.digest_path(path)
        task = await self.operation("files.patch", {"file": str(path), "offset": "80000", "delete_count": "3",
                                                    "content": "nuevo", "expected_sha256": digest})
        self.assertEqual(path.read_text(), content)
        self.assertEqual(task["status"], "WAITING_APPROVAL")
        task = await self.approve(task)
        self.assertEqual(task["status"], "COMPLETED")
        self.assertEqual(path.read_text(), "á" * 80000 + "nuevo" + "fin" * 30000)
        with self.assertRaises(ArgosError):
            await fs.files_patch(None, {"file": str(path), "offset": "0", "delete_count": "0",
                                        "content": "x", "expected_sha256": digest})

    async def test_credentials_after_first_page_are_not_exposed(self):
        path = self.root / "report.txt"
        path.write_text("a" * 100000 + "\npassword=do-not-persist")
        with self.assertRaises(ArgosError):
            await fs.files_read(None, {"file": str(path)})
        path.write_text("a" * 32764 + "\npassword=do-not-persist")
        with self.assertRaises(ArgosError):
            await fs.files_read(None, {"file": str(path)})

    async def test_hidden_config_is_accessible_but_symlinks_and_credentials_are_not(self):
        path = self.root / ".editorconfig"
        path.write_text("root = true\n")
        self.assertIn("root = true", (await fs.files_read(None, {"file": str(path)}))["evidence"]["content"])
        (self.root / "link").symlink_to(path)
        for blocked in (self.root / "link", self.root / ".env"):
            with self.assertRaises((OSError, ArgosError)):
                await fs.files_read(None, {"file": str(blocked)})
        with self.assertRaises(ArgosError):
            await fs.files_read(None, {"file": "relative.txt"})

    async def test_directory_pages_reach_all_entries(self):
        directory = self.root / "many"
        directory.mkdir()
        for i in range(160):
            (directory / f"{i:03}.txt").touch()
        first = await fs.files_list(None, {"path": str(directory)})
        second = await fs.files_list(None, {"path": str(directory), "offset": first["next_offset"]})
        self.assertEqual(len(first["evidence"]) + len(second["evidence"]), 160)
        self.assertIsNone(second["next_offset"])

    async def test_copy_move_trash_and_restore_tree(self):
        source, copied, moved = [self.root / n for n in ("source", "copied", "moved")]
        await fs.files_mkdir(None, {"path": str(source)})
        (source / "binary.bin").write_bytes(bytes(range(256)) * 400)
        digest = fs.digest_path(source)
        result = await fs.files_copy(None, {"source": str(source), "destination": str(copied), "expected_sha256": digest})
        self.assertEqual(result["verification"], "copy_verified")
        await fs.files_move(None, {"source": str(copied), "destination": str(moved), "expected_sha256": digest})
        task = await self.operation("files.delete", {"path": str(moved), "expected_sha256": digest})
        self.assertTrue(moved.exists())
        task = await self.approve(task)
        self.assertEqual(task["status"], "COMPLETED")
        self.assertFalse(moved.exists())
        destination = task["result"]["evidence"]["destination"]
        await fs.files_move(None, {"source": destination, "destination": str(moved), "expected_sha256": digest})
        self.assertEqual((source / "binary.bin").read_bytes(), (moved / "binary.bin").read_bytes())

    async def test_no_overwrite_or_stale_tree_removal(self):
        source, destination = self.root / "source.txt", self.root / "destination.txt"
        source.write_text("original")
        destination.write_text("user data")
        digest = fs.digest_path(source)
        for operation in (fs.files_copy, fs.files_move):
            with self.assertRaises(FileExistsError):
                await operation(None, {"source": str(source), "destination": str(destination), "expected_sha256": digest})
        self.assertEqual(destination.read_text(), "user data")
        task = await self.operation("files.delete", {"path": str(source), "expected_sha256": digest})
        source.write_text("new edit")
        task = await self.approve(task)
        self.assertEqual(task["status"], "FAILED")
        self.assertEqual(source.read_text(), "new edit")

    async def test_project_bootstrap_then_relative_write_same_task(self):
        root = self.root / "new-project"
        observations = []
        class Provider:
            name = "fake"
            async def work(provider, task, context, execute, save_thread, progress):
                observations.append(context["project"])
                save_thread("same-thread")
                if not root.exists():
                    await execute("projects.create", {"name": "New", "path": str(root)})
                elif not (root / "hello.py").exists():
                    await execute("files.write", {"file": "hello.py", "content": "print('hello')\n", "expected_sha256": ""})
                return {"kind": "result", "speech": "Proyecto preparado.", "detail": ""}
        self.core.interpreter = Provider()
        response = await self.req("say", text="programacion: crea un proyecto desde cero")
        task = await self.settled(response["task_id"])
        self.assertEqual(task["status"], "WAITING_APPROVAL")
        self.assertFalse(root.exists())
        task = await self.approve(task)
        self.assertEqual(task["status"], "WAITING_APPROVAL")
        self.assertEqual(self.store.project(task["project"])["root"], str(root))
        task = await self.approve(task)
        self.assertEqual(task["status"], "COMPLETED")
        self.assertEqual(task["thread_id"], "same-thread")
        self.assertEqual((root / "hello.py").read_text(), "print('hello')\n")
        self.assertIsNone(observations[0])
        self.assertEqual(observations[1]["root"], str(root))

    async def test_command_without_registration_is_reviewed_and_executed_in_cwd(self):
        task = await self.operation("commands.exec", {"cwd": str(self.root),
                                     "argv_json": json.dumps([sys.executable, "-c", "print('checked')"])})
        self.assertEqual(task["status"], "WAITING_APPROVAL")
        self.assertEqual(task["result"]["pending_operation"]["review"]["cwd"], str(self.root))
        task = await self.approve(task)
        self.assertEqual(task["status"], "COMPLETED")
        self.assertEqual(task["result"]["evidence"]["stdout"], "checked\n")

    async def test_workspace_is_approved_and_launch_is_not_a_completion_claim(self):
        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=SimpleNamespace(returncode=None))) as spawn:
            task = await self.operation("workspace.open", {"path": str(self.root), "editor": "codex"})
            spawn.assert_not_called()
            task = await self.approve(task)
        self.assertEqual(task["result"]["verification"], "workspace_dispatched")
        self.assertEqual(spawn.call_args.args, ("kitty", "--directory", str(self.root), "codex", "-C", str(self.root)))

    async def test_spoken_review_challenge_exact_once_and_session_bound(self):
        target = self.root / "new-dir"
        task = await self.operation("files.mkdir", {"path": str(target)})
        reviewed = await self.req("say", text="revisa la aprobación")
        self.assertIn(str(target), reviewed["speech"])
        code = self.core.approval_dialog.challenges["default"]["code"]
        for request in ({"text": "aprueba incorrecto"}, {"text": "aprueba " + code, "session": "other"}):
            with self.assertRaises(ArgosError):
                await self.req("say", **request)
        await self.req("say", text="sí")
        self.assertFalse(target.exists())
        await self.req("say", text="aprueba " + code)
        self.assertEqual((await self.settled(task["id"]))["status"], "COMPLETED")
        with self.assertRaises(ArgosError):
            await self.req("say", text="aprueba " + code)

    async def test_spoken_challenge_expires_and_multiple_tasks_need_selection(self):
        task = await self.operation("files.mkdir", {"path": str(self.root / "a")})
        await self.operation("files.mkdir", {"path": str(self.root / "b")})
        with self.assertRaises(ArgosError):
            await self.req("say", text="revisa aprobación")
        await self.req("say", text="revisa aprobación " + task["id"][:8])
        challenge = self.core.approval_dialog.challenges["default"]
        challenge["expires"] = 0
        with self.assertRaises(ArgosError):
            await self.req("say", text="aprueba " + challenge["code"])
        self.assertFalse((self.root / "a").exists())

    async def test_spoken_approval_is_invalid_after_cancel_or_pending_change(self):
        task = await self.operation("files.mkdir", {"path": str(self.root / "a")})
        await self.req("say", text="revisa aprobación")
        code = self.core.approval_dialog.challenges["default"]["code"]
        await self.req("cancel", task_id=task["id"])
        with self.assertRaises(ArgosError):
            await self.req("say", text="aprueba " + code)

    async def test_mutation_retry_does_not_replay(self):
        message = {"method": "run", "capability": "files.mkdir", "arguments": {"path": str(self.root / "once")},
                   "request_id": "create-once-only"}
        result = await self.core.request(message)
        task = await self.settled(result["task_id"])
        await self.approve(task)
        repeated = await self.core.request(message)
        self.assertEqual(repeated, result)
        self.assertEqual(len(self.store.tasks()), 1)

    async def test_cancel_waits_for_disk_effect_and_records_evidence_without_blocking_status(self):
        from dataclasses import replace
        from argos.capabilities import CAPABILITIES
        entered, release = threading.Event(), threading.Event()
        target = self.root / "atomic-step"
        async def slow_create(project, args):
            entered.set()
            release.wait(3)
            target.mkdir()
            return fs.outcome("Creado.", {"path": str(target)}, "directory_created")
        slow_create.__module__ = "argos.filesystem"
        original = CAPABILITIES["files.mkdir"]
        with patch.dict(CAPABILITIES, {"files.mkdir": replace(original, execute=slow_create)}):
            task = await self.operation("files.mkdir", {"path": str(target)})
            await self.req("approve", task_id=task["id"],
                           fingerprint=task["result"]["pending_operation"]["fingerprint"])
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait, 2))
                await asyncio.wait_for(self.req("tasks"), .5)
                cancellation = asyncio.create_task(self.req("cancel", task_id=task["id"]))
                await asyncio.sleep(.02)
                self.assertFalse(cancellation.done())
            finally:
                release.set()
            await cancellation
            task = await self.settled(task["id"])
        self.assertEqual(task["status"], "CANCELLED")
        self.assertTrue(target.exists())
        self.assertTrue(any(e["kind"] == "CAPABILITY_RESULT" for e in self.store.events(task["id"])))

    async def test_recovery_never_replays_project_creation(self):
        target = self.root / "new-project"
        task = await self.operation("projects.create", {"name": "New", "path": str(target)})
        task = await self.approve(task)
        self.assertEqual(task["status"], "COMPLETED")
        await self.core.close()
        self.core = Core(self.store)
        await self.core.start()
        self.assertEqual(self.store.project("New")["root"], str(target))
        self.assertTrue(self.core.queue.empty())
