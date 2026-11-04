import asyncio
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from argos.core import Core
from argos.filesystem import project_locations, observe_project_folders
from argos.models import ArgosError, Decision
from argos.store import Store


class ProjectRegistrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)
        self.home_patch = patch("pathlib.Path.home", return_value=self.home)
        self.home_patch.start()
        self.base = self.home / "Proyectos"
        self.folder = self.base / "Faro"
        self.folder.mkdir(parents=True)
        (self.folder / "notes.txt").write_text("existing work")
        self.store = Store(self.home / "state")
        self.core = Core(self.store)
        await self.core.start()

    async def asyncTearDown(self):
        await self.core.close()
        self.store.close()
        self.home_patch.stop()
        self.temp.cleanup()

    async def request(self, method, **kwargs):
        return await self.core.request({"method": method, "request_id": uuid.uuid4().hex, **kwargs})

    async def settle(self, response):
        await asyncio.wait_for(self.core.queue.join(), 5)
        return self.store.task(response["task_id"])

    async def register(self, name="Faro", path=None):
        return await self.settle(await self.request("run", capability="projects.register",
            arguments={"name": name, "path": str(path or self.folder)}))

    async def test_locations_are_observed_and_available_to_all_roles(self):
        self.store.add_project("Faro", self.folder)
        for agent in ("general", "computer", "engineering"):
            locations = self.core.context(None, agent)["filesystem"]["project_locations"]
            self.assertEqual(locations["default"], str(self.base))
            self.assertEqual(locations["candidates"], [{"path": str(self.base),
                "sources": ["home_convention", "registered_project_parent"]}])
            self.assertEqual(locations["registered"], [{"name": "Faro", "root": str(self.folder)}])
        (self.home / "Projects").mkdir()
        self.assertIsNone(project_locations(self.store.projects())["default"])

    async def test_no_assumed_linux_default_and_custom_registered_parent(self):
        with patch("pathlib.Path.home", return_value=self.home / "other-home"):
            self.assertEqual(project_locations([])["candidates"], [])
            self.assertIsNone(project_locations([])["default"])
            self.store.add_project("Faro", self.folder)
            self.assertEqual(project_locations(self.store.projects())["default"], str(self.base))

    async def test_register_preserves_files_and_is_idempotent_with_task_evidence(self):
        before = (self.folder / "notes.txt").stat()
        first = await self.register()
        second = await self.register(name="faro")
        for task in (first, second):
            self.assertEqual(task["status"], "COMPLETED")
            self.assertEqual(task["agent"], "computer")
            self.assertEqual(task["result"]["verification"], "project_registered")
            self.assertEqual(task["result"]["evidence"]["project"]["id"], task["project"])
        self.assertEqual(first["project"], second["project"])
        self.assertEqual(len(self.store.projects()), 1)
        self.assertEqual(list(self.folder.iterdir()), [self.folder / "notes.txt"])
        self.assertEqual((self.folder / "notes.txt").read_text(), "existing work")
        self.assertEqual((self.folder / "notes.txt").stat().st_mtime_ns, before.st_mtime_ns)

    async def test_missing_folder_does_not_create_or_register_anything(self):
        missing = self.base / "missing"
        task = await self.register(path=missing)
        self.assertEqual(task["status"], "FAILED")
        self.assertFalse(missing.exists())
        self.assertEqual(self.store.projects(), [])
        self.assertFalse(any(e["kind"] == "CAPABILITY_RESULT" for e in self.store.events(task["id"])))

    async def test_conflicts_do_not_rename_or_retarget(self):
        await self.register()
        other = self.base / "Other"
        other.mkdir()
        self.assertEqual((await self.register(name="Other"))["status"], "FAILED")
        self.assertEqual((await self.register(path=other))["status"], "FAILED")
        self.assertEqual([(p["name"], p["root"]) for p in self.store.projects()], [("Faro", str(self.folder))])

    async def test_registration_and_discovery_reject_links_and_protected_paths(self):
        link = self.home / "Projects"
        link.symlink_to(self.base)
        private = self.home / ".ssh" / "work"
        private.mkdir(parents=True)
        for path in (link / "Faro", private, self.home, Path("/"), self.folder / "notes.txt",
                     self.base / ".." / "Proyectos" / "Faro"):
            with self.subTest(path=path):
                with self.assertRaises(ArgosError):
                    self.store.add_project("Blocked", path)
        self.assertEqual(project_locations([])["default"], str(self.base))
        self.assertEqual(self.store.projects(), [])

    async def test_contextual_registration_uses_one_decision_and_english_result(self):
        seen = []
        class Provider:
            name = "fixture"
            async def decide(provider, text, context, agent="general"):
                seen.append(context)
                return Decision("capability", agent="computer", capability="projects.register",
                    arguments={"name": "Faro", "path": context["filesystem"]["project_locations"]["default"] + "/Faro"})
        self.core.interpreter = Provider()
        task = await self.settle(await self.request("say", text="Register Faro in my Linux projects directory."))
        self.assertEqual(len(seen), 1)
        self.assertEqual(task["status"], "COMPLETED")
        self.assertEqual(task["result"]["speech"], "Project Faro registered.")
        self.assertEqual(self.store.projects()[0]["root"], str(self.folder))

    async def test_specialist_can_read_relative_path_after_registration_without_global_focus(self):
        observed = []
        class Provider:
            name = "fixture"
            async def decide(provider, text, context, agent="general"):
                return Decision("delegate", agent="computer")
            async def work(provider, task, context, execute, save_thread, progress):
                await execute("projects.register", {"name": "Faro", "path": str(self.folder)})
                observed.append(context["project"]["root"])
                observed.append((await execute("files.read", {"file": "notes.txt"}))["evidence"]["content"])
                return {"kind": "result", "speech": "Registered and read.", "detail": ""}
        self.core.interpreter = Provider()
        task = await self.settle(await self.request("say", text="Register Faro and read its notes."))
        self.assertEqual(task["status"], "COMPLETED")
        self.assertEqual(observed, [str(self.folder), "existing work"])
        self.assertIsNone(self.core.context(None)["project"])

    async def test_creation_still_requires_approval(self):
        path = self.base / "New"
        task = await self.settle(await self.request("run", capability="projects.create",
            arguments={"name": "New", "path": str(path)}))
        self.assertEqual(task["status"], "WAITING_APPROVAL")
        self.assertFalse(path.exists())
        self.assertEqual(self.store.projects(), [])

    async def test_registration_does_not_authorize_following_write(self):
        class Provider:
            name = "fixture"
            async def decide(provider, text, context, agent="general"):
                return Decision("delegate", agent="computer")
            async def work(provider, task, context, execute, save_thread, progress):
                await execute("projects.register", {"name": "Faro", "path": str(self.folder)})
                await execute("files.write", {"file": "new.txt", "content": "proposed", "expected_sha256": ""})
                raise AssertionError("An unapproved write must suspend the task")
        self.core.interpreter = Provider()
        task = await self.settle(await self.request("say", text="Register Faro and write new.txt in it."))
        self.assertEqual(task["status"], "WAITING_APPROVAL")
        self.assertEqual(self.store.project(task["project"])["root"], str(self.folder))
        self.assertFalse((self.folder / "new.txt").exists())
        self.assertEqual(task["result"]["pending_operation"]["capability"], "files.write")

    async def test_context_includes_unregistered_folders_not_protected_or_linked_entries(self):
        (self.base / "some-and-co2").mkdir()
        (self.base / "private-key-backup").mkdir()
        (self.base / ".hidden").mkdir()
        (self.base / "alias").symlink_to(self.folder)
        (self.base / "readme.txt").write_text("not a directory")
        locations = self.core.context(None)["filesystem"]["project_locations"]
        self.assertEqual(locations["registered"], [])
        listing = locations["directories"][0]
        self.assertEqual([item["name"] for item in listing["entries"]], ["Faro", "some-and-co2"])
        self.assertFalse(listing["truncated"])
        self.assertGreater(listing["observed_at"], 0)
        saved = self.store.add_project("Faro", self.folder)
        for role in ("computer", "engineering"):
            self.assertEqual(self.core.context(saved, role)["filesystem"]["project_locations"]["directories"], [])

    async def test_folder_observation_is_bounded_and_marks_partial_or_unavailable(self):
        for index in range(65):
            (self.base / f"folder-{index}").mkdir()
        listing = observe_project_folders(self.base)
        self.assertEqual(len(listing["entries"]), 50)
        self.assertTrue(listing["truncated"])
        missing = observe_project_folders(self.base / "missing")
        self.assertEqual(missing["status"], "unavailable")
        self.assertTrue(missing["truncated"])

    async def test_list_results_are_available_in_later_general_context_but_scoped(self):
        response = await self.request("run", capability="files.list", arguments={"path": str(self.base)})
        await self.settle(response)
        observed = self.core.task_context("default", observations=True)[0]["observed_directory"]
        self.assertEqual(observed["entries"], [{"name": "Faro", "directory": True}])
        self.assertEqual(observed["path"], str(self.base))
        self.assertEqual(self.core.task_context("other", observations=True), [])
        registered = self.store.add_project("Faro", self.folder)
        self.assertNotIn("observed_directory", self.core.task_context("default", observations=True, project=registered)[0])

    async def test_delegated_correction_receives_frozen_history_and_listing(self):
        observed = []
        class Provider:
            name = "fixture"
            async def decide(provider, text, context, agent="general"):
                if text == "Some underscore CO2.":
                    return Decision("delegate", agent="computer")
                return Decision("clarify", speech="Which existing folder?")
            async def work(provider, task, context, execute, save_thread, progress):
                observed.append(context["conversation_handoff"])
                return {"kind": "question", "speech": "A scoped question.", "detail": ""}
        self.core.interpreter = Provider()
        await self.request("say", text="Register my CO2 project in my Linux projects folder.")
        await self.settle(await self.request("run", capability="files.list", arguments={"path": str(self.base)}))
        response = await self.request("say", text="Some underscore CO2.")
        await self.settle(response)
        self.assertEqual(observed[0]["recent_conversation"][0]["content"], "Register my CO2 project in my Linux projects folder.")
        self.assertEqual(observed[0]["directory_observations"][0]["path"], str(self.base))
        frozen = self.store.events(response["task_id"])
        await self.request("say", text="Unrelated future request.")
        self.assertEqual(self.store.events(response["task_id"]), frozen)
        response = await self.request("say", text="Some underscore CO2.", session="other")
        await self.settle(response)
        self.assertEqual(observed[1], {"recent_conversation": [], "directory_observations": []})
