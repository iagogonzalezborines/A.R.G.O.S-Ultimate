import asyncio
import copy
import json
import os
import sys
import tempfile
import time
import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock, patch

from argos.capabilities import CAPABILITIES
from argos.core import Core
from argos.host import LinuxEnvironment, TOOLS, collect_local, observation
from argos.models import Decision
from argos.store import Store


def local_facts():
    return {"system": observation({"distribution": "Test Linux"}, "fixture"),
            "tools": observation({tool: tool in ("python", "python3", "git", "code") for tool in TOOLS}, "PATH fixture"),
            "session": observation({"display_present": True, "hyprland_indicated": False}, "session fixture"),
            "memory": observation({"MemTotal": 8 * 1024**3}, "memory fixture")}


class HostEnvironmentTests(unittest.IsolatedAsyncioTestCase):
    async def environment(self):
        environment = LinuxEnvironment()
        with patch("argos.host.collect_local", side_effect=local_facts):
            await environment.refresh()
        return environment

    async def test_missing_dependencies_and_operation_specific_workspace_readiness(self):
        environment = await self.environment()
        status = lambda name, args=None: environment.capability_status(CAPABILITIES[name], arguments=args)
        self.assertFalse(status("windows.list")["available"])
        self.assertIn("hyprctl", status("windows.list")["reason"])
        self.assertIsNone(status("workspace.open", {"editor": "code"})["available"])
        self.assertFalse(status("workspace.open", {"editor": "codex"})["available"])
        self.assertIn("kitty", status("workspace.open", {"editor": "codex"})["reason"])
        self.assertEqual(status("repo.inspect")["status"], "needs_context")
        self.assertIsNone(status("web.read")["available"])
        self.assertTrue(status("system.inspect")["available"])
        self.assertIsNone(CAPABILITIES["windows.list"].public()["available"])

    async def test_stale_inventory_is_not_claimed_current_and_refresh_detects_changes(self):
        environment = await self.environment()
        environment.updated -= 60
        self.assertTrue(environment.snapshot()["stale"])
        self.assertIsNone(environment.capability_status(CAPABILITIES["system.info"])["available"])
        changed = local_facts()
        changed["tools"]["value"]["code"] = False
        with patch("argos.host.collect_local", return_value=changed):
            await environment.refresh()
        self.assertFalse(environment.snapshot()["stale"])
        self.assertFalse(environment.capability_status(CAPABILITIES["workspace.open"])["available"])
        snapshot = environment.snapshot()
        snapshot["facts"].clear()
        self.assertTrue(environment.snapshot()["facts"])

    async def test_parallel_requests_share_observation_and_no_external_network_probe(self):
        environment = LinuxEnvironment()
        with patch("argos.host.collect_local", side_effect=local_facts) as collect, \
             patch("argos.linux_tools.process", AsyncMock()) as process:
            await asyncio.gather(*(environment.refresh() for _ in range(10)))
            collect.assert_called_once()
            process.assert_not_called()
            await environment.refresh(force=True)
            self.assertEqual(collect.call_count, 2)

    async def test_audio_and_compositor_probes_only_query_metadata_and_report_partial_failures(self):
        facts = local_facts()
        facts["tools"]["value"].update(pactl=True, hyprctl=True)
        facts["session"]["value"]["hyprland_indicated"] = True
        async def process(argv, **kwargs):
            self.assertLessEqual(kwargs["timeout"], 1)
            if argv == ["hyprctl", "-j", "monitors"]:
                raise PermissionError()
            if argv == ["pactl", "-f", "json", "list", "sources"]:
                return 0, json.dumps([{"name": "mic", "description": "Headset", "private": "not exposed"}]), ""
            self.assertEqual(argv, ["pactl", "-f", "json", "list", "sinks"])
            raise TimeoutError()
        environment = LinuxEnvironment()
        with patch("argos.host.collect_local", return_value=facts), \
             patch("argos.linux_tools.process", side_effect=process) as command:
            await environment.refresh()
        self.assertEqual(command.call_count, 3)
        facts = environment.snapshot()["facts"]
        self.assertEqual(facts["windows"]["status"], "permission_denied")
        self.assertEqual(facts["audio_sinks"]["status"], "not_checked")
        self.assertEqual(facts["audio_sources"]["value"], [{"name": "mic", "description": "Headset"}])
        self.assertFalse(environment.capability_status(CAPABILITIES["windows.list"])["available"])

    async def test_probe_success_and_failure_do_not_confuse_installation_with_connection(self):
        facts = local_facts()
        facts["tools"]["value"]["hyprctl"] = True
        facts["session"]["value"]["hyprland_indicated"] = True
        environment = LinuxEnvironment()
        with patch("argos.host.collect_local", return_value=facts), \
             patch("argos.linux_tools.process", AsyncMock(return_value=(0, "[]", ""))):
            await environment.refresh()
        self.assertTrue(environment.capability_status(CAPABILITIES["windows.list"])["available"])
        with patch("argos.host.collect_local", return_value=facts), \
             patch("argos.linux_tools.process", AsyncMock(return_value=(1, "", "private error"))):
            await environment.refresh(force=True)
        self.assertIsNone(environment.capability_status(CAPABILITIES["windows.list"])["available"])
        self.assertNotIn("private error", json.dumps(environment.snapshot()))

    def test_collector_is_allowlisted_bounded_and_omits_secrets(self):
        reads = []
        def read(path, limit=65536):
            reads.append(str(path))
            if str(path) == "/proc/cpuinfo":
                return "model name : Test CPU\nSerial : private-serial\n"
            if str(path) == "/proc/meminfo":
                raise PermissionError()
            raise AssertionError(path)
        with patch("argos.host.read_text", side_effect=read), \
             patch("argos.host.platform.freedesktop_os_release", return_value={"PRETTY_NAME": "Test Linux"}), \
             patch("pathlib.Path.glob", return_value=[]), \
             patch.dict(os.environ, {"UNRELATED_SECRET": "do-not-copy", "XDG_CURRENT_DESKTOP": "password=do-not-copy"}):
            facts = collect_local()
        serialized = json.dumps(facts)
        self.assertNotIn("do-not-copy", serialized)
        self.assertNotIn("private-serial", serialized)
        self.assertEqual(facts["memory"]["status"], "permission_denied")
        self.assertEqual(facts["session"]["status"], "unavailable")
        self.assertEqual(facts["cpu"]["value"]["model"], "Test CPU")
        self.assertEqual(set(reads), {"/proc/cpuinfo", "/proc/meminfo"})
        self.assertEqual(facts["network"]["status"], "not_checked")


class HostContextTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root / "state")
        self.environment = LinuxEnvironment()
        self.collect = patch("argos.host.collect_local", side_effect=local_facts)
        self.collect.start()
        self.core = Core(self.store, environment=self.environment)
        await self.core.start()

    async def asyncTearDown(self):
        await self.core.close()
        self.store.close()
        self.collect.stop()
        self.temp.cleanup()

    async def req(self, method, **kwargs):
        return await self.core.request({"method": method, "request_id": uuid.uuid4().hex, **kwargs})

    async def settled(self, task_id):
        await asyncio.wait_for(self.core.queue.join(), 5)
        return self.store.task(task_id)

    async def test_inventory_poll_does_not_write_database_and_context_reaches_general(self):
        before = self.store.db.total_changes
        report = (await self.req("environment.inspect", refresh=True))["data"]
        self.assertEqual(self.store.db.total_changes, before)
        self.assertEqual(report["environment"]["facts"]["system"]["value"]["distribution"], "Test Linux")
        seen = []
        class Provider:
            name = "test"
            async def decide(provider, text, context, agent="general"):
                seen.append(context)
                return Decision("answer", "Tengo 8 GiB de RAM observados.")
        self.core.interpreter = Provider()
        await self.req("say", text="Describe el equipo en el que estás")
        self.assertEqual(seen[0]["environment"]["facts"]["memory"]["value"]["MemTotal"], 8 * 1024**3)
        windows = next(c for c in seen[0]["capabilities"] if c["name"] == "windows.list")
        self.assertFalse(windows["available"])

    async def test_known_unavailable_operation_is_rejected_before_approval_or_launch(self):
        with patch("asyncio.create_subprocess_exec", AsyncMock()) as launch:
            response = await self.req("run", capability="workspace.open", arguments={"path": str(self.root), "editor": "codex"})
            task = await self.settled(response["task_id"])
        self.assertEqual(task["status"], "FAILED")
        self.assertIn("kitty", task["question"] or str(task["result"]))
        launch.assert_not_called()
        self.assertFalse(any(e["kind"] == "CAPABILITY_STARTED" for e in self.store.events(task["id"])))

    async def test_natural_inspection_updates_evidence_and_shared_snapshot(self):
        response = await self.req("say", text="inspecciona el equipo")
        task = await self.settled(response["task_id"])
        self.assertEqual(task["status"], "COMPLETED")
        self.assertEqual(task["result"]["evidence"]["observed_at"], self.environment.snapshot()["observed_at"])
        self.assertEqual(task["result"]["verification"], "host_observed")

    async def test_text_workflow_inspects_researches_and_builds_temporary_project_with_approvals(self):
        project = self.root / "new-project"
        contexts = []
        class Provider:
            name = "scripted-test"
            async def work(provider, task, context, execute, save_thread, progress):
                contexts.append(copy.deepcopy(context))
                save_thread("same-project-thread")
                done = {entry["capability"] for entry in context.get("previous_operations", [])}
                if "system.inspect" not in done:
                    await execute("system.inspect", {})
                    await execute("web.search", {"query": "official project example"})
                    for url in ("https://one.example/", "https://two.example/"):
                        await execute("web.read", {"url": url, "offset": "0", "expected_sha256": ""})
                if "projects.create" not in done:
                    await execute("projects.create", {"name": "Demo", "path": str(project)})
                if "files.write" not in done:
                    await execute("files.write", {"file": "hello.py", "content": "value = 42\n", "expected_sha256": ""})
                if "commands.exec" not in done:
                    await execute("commands.exec", {"cwd": str(project), "argv_json": json.dumps([
                        sys.executable, "-c", "from pathlib import Path; assert Path('hello.py').read_text() == 'value = 42\\n'; print('verified')"])})
                return {"kind": "result", "speech": "Proyecto comprobado.",
                        "detail": "Fuentes: https://one.example/ y https://two.example/"}
        self.core.interpreter = Provider()
        search = AsyncMock(return_value={"speech": "Fuentes encontradas.", "evidence": [], "verification": "search_results_received"})
        with patch.dict(CAPABILITIES, {"web.search": replace(CAPABILITIES["web.search"], execute=search)}), \
             patch("argos.web_reader.fetch", side_effect=lambda url: (url, "text/plain", "Example from " + url)):
            response = await self.req("say", text="programacion: inspecciona el equipo, investiga y crea un proyecto")
            task = await self.settled(response["task_id"])
            self.assertFalse(project.exists())
            approvals = []
            while task["status"] == "WAITING_APPROVAL":
                operation = task["result"]["pending_operation"]
                approvals.append(operation["capability"])
                self.assertLessEqual(len(approvals), 3)
                await self.req("approve", task_id=task["id"], fingerprint=operation["fingerprint"])
                task = await self.settled(task["id"])
        self.assertEqual(approvals, ["projects.create", "files.write", "commands.exec"])
        self.assertEqual(task["status"], "COMPLETED")
        self.assertEqual(task["result"]["verification"], "command_passed")
        self.assertEqual(task["thread_id"], "same-project-thread")
        self.assertEqual((project / "hello.py").read_text(), "value = 42\n")
        search.assert_awaited_once()
        self.assertTrue(all(c["environment"]["facts"]["memory"]["value"] for c in contexts))
        events = [e for e in self.store.events(task["id"]) if e["kind"] == "CAPABILITY_RESULT"]
        self.assertEqual(len(events), 7)
