import asyncio
import json
from pathlib import Path
import shutil
import socket
import tempfile
import unittest
import uuid
from unittest.mock import AsyncMock, Mock, patch

from argos.core import Core
from argos.development import Development
from argos.development_workspace import LinuxDevelopmentWorkspace
from argos.models import ArgosError, Decision, Status
from argos.providers import validate_decision
from argos.store import Store


class Programmer:
    name = "scripted-codex"

    def __init__(self):
        self.contexts = []
        self.checks = [["python3", "-m", "unittest", "discover", "-s", "tests", "-v"]]
        self.started, self.release = asyncio.Event(), asyncio.Event()
        self.release.set()
        self.attack = None
        self.before_plan = None
        self.skip_checks = False
        self.edit_after_checks = False
        self.skip_review = False
        self.final = "La mejora de cálculo está preparada y probada en la candidata; falta activarla."
        self.plan_speech = "Añadiré el cálculo y su prueba en una copia aislada, sin activarla. ¿Adelante?"

    async def decide(self, text, context, agent="general"):
        self.contexts.append(context)
        if text == "¿Cómo va esa mejora?":
            return Decision("task_status", arguments={"task_id": context["tasks"][0]["id"]})
        if text == "implementa la mejora en ti mismo":
            return Decision("develop", arguments={"target": "self"})
        return Decision("answer", speech="Sí, podemos seguir hablando.")

    async def work(self, task, context, execute, save_thread, progress):
        self.contexts.append(context)
        save_thread(task.get("thread_id") or "thread-" + task["id"])
        if not context["development"]["authorized"]:
            if self.before_plan:
                await execute(*self.before_plan)
            await execute("files.list", {"path": "."})
            await execute("development.plan", {"content": json.dumps({"speech": self.plan_speech,
                          "steps": ["Implementar el cálculo", "Añadir una prueba de regresión"], "checks": self.checks})})
        self.started.set()
        await self.release.wait()
        if self.attack:
            await execute(*self.attack)
        await execute("files.write", {"file": "feature.py", "content": "value = 42\n", "expected_sha256": ""})
        await execute("files.mkdir", {"path": "tests"})
        await execute("files.write", {"file": "tests/test_feature.py", "expected_sha256": "",
                      "content": "import unittest\nfrom feature import value\nclass Feature(unittest.TestCase):\n    def test_value(self):\n        self.assertEqual(value, 42)\n"})
        progress("Los archivos de cálculo y su prueba están escritos en la candidata.")
        if not self.skip_checks:
            for index in range(len(self.checks)):
                await execute("development.check", {"index": str(index)})
        if self.edit_after_checks:
            await execute("files.write", {"file": "after.py", "content": "changed = True\n", "expected_sha256": ""})
        if not self.skip_review:
            await execute("development.review", {})
        return {"kind": "result", "speech": self.final, "detail": "Cálculo y prueba preparados."}


class DevelopmentTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        (self.source / "src/argos").mkdir(parents=True)
        (self.source / "src/argos/core.py").write_text("# fixture, never real ARGOS\n")
        self.store = Store(self.root / "state")
        self.project = self.store.add_project("demo", str(self.source))
        self.adapter = LinuxDevelopmentWorkspace(self.store.directory, self.source)
        self.adapter.check = AsyncMock(return_value={"argv": ["python3"], "exit_code": 0, "output": "OK",
                                                     "verification": "command_passed", "isolation": "test-double"})
        self.development = Development(self.store, self.adapter)
        self.provider = Programmer()
        self.core = Core(self.store, self.provider, development=self.development)
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

    async def plan(self, target="project", **kwargs):
        response = await self.req("develop", text="Añadir cálculo", target=target,
                                  project=self.project["id"], **kwargs)
        task = await self.settled(response["task_id"])
        self.assertEqual(task["status"], Status.WAITING_APPROVAL, task)
        return task

    async def approve(self, task):
        return await self.req("approve", task_id=task["id"], fingerprint=task["result"]["pending_plan"]["fingerprint"])

    async def test_one_plan_authorizes_multiple_edits_checks_and_natural_completion(self):
        task = await self.plan()
        state = self.development.state(task["id"])
        candidate = Path(state["workspace"])
        self.assertFalse((candidate / "feature.py").exists())
        self.assertNotIn(task["id"], self.development.grants)
        original_thread = task["thread_id"]
        await self.approve(task)
        done = await self.settled(task["id"])
        self.assertEqual(done["status"], "COMPLETED", done)
        self.assertEqual(done["thread_id"], original_thread)
        self.assertEqual(done["result"]["verification"], "command_passed")
        self.assertEqual((candidate / "feature.py").read_text(), "value = 42\n")
        self.assertFalse((self.source / "feature.py").exists())
        self.assertFalse(done["result"]["activated"])
        self.assertTrue(Path(done["result"]["patch"]).is_file())
        self.assertIn("value = 42", Path(done["result"]["patch"]).read_text())
        self.assertEqual(self.core.notifications[-1]["speech"], self.provider.final)
        self.assertEqual(sum(e["kind"] == "PLAN_APPROVED" for e in self.store.events(task["id"])), 1)
        self.assertNotIn(task["id"], self.development.grants)
        self.assertFalse(self.core.policy._approved)
        status = await self.req("say", text="¿Cómo va esa mejora?")
        self.assertIn("Las pruebas acordadas pasaron", status["speech"])
        self.assertIn("No se ha aplicado", status["speech"])
        self.assertNotIn(task["objective"], status["speech"])

    async def test_end_to_end_with_actual_isolated_unittest(self):
        if not shutil.which("bwrap"):
            self.skipTest("bubblewrap not installed")
        self.adapter.check = LinuxDevelopmentWorkspace.check.__get__(self.adapter)
        task = await self.plan()
        probe = await self.adapter.check(self.development.state(task["id"]), ["true"])
        if probe["exit_code"]:
            self.skipTest("bubblewrap namespaces unavailable")
        await self.approve(task)
        done = await self.settled(task["id"])
        self.assertEqual(done["status"], "COMPLETED", done)
        check = done["result"]["checks"][0]
        self.assertEqual(check["exit_code"], 0)
        self.assertIn("Ran 1 test", check["output"])
        self.assertFalse((self.source / "feature.py").exists())

    async def test_idempotent_confirmation_does_not_repeat_work(self):
        task = await self.plan()
        request = {"method": "approve", "request_id": uuid.uuid4().hex, "task_id": task["id"],
                   "fingerprint": task["result"]["pending_plan"]["fingerprint"]}
        first = await self.core.request(request)
        done = await self.settled(task["id"])
        again = await self.core.request(request)
        self.assertEqual(first, again)
        self.assertEqual(self.store.task(task["id"]), done)
        self.assertEqual(self.adapter.check.await_count, 1)

    async def test_voice_yes_only_after_complete_plan_playback(self):
        voice = Mock()
        self.core.speech = voice
        task = await self.plan()
        calls = [c for c in voice.enqueue.call_args_list if "on_complete" in c.kwargs]
        self.assertEqual(calls[0].args[0], self.provider.plan_speech)
        await self.req("say", text="sí")
        self.assertEqual(self.store.task(task["id"])["status"], "WAITING_APPROVAL")
        calls[0].kwargs["on_complete"]()
        response = await self.req("say", text="sí", conversation=True)
        self.assertEqual(response["task_id"], task["id"])
        self.assertEqual((await self.settled(task["id"]))["status"], "COMPLETED")

    async def test_unrelated_turn_interruption_expiry_and_other_session_do_not_confirm(self):
        task = await self.plan()
        for extra in ({"speech_interrupted": True}, {"session": "other"}):
            self.development.present(task["id"])
            await self.req("say", text="sí", **extra)
            self.assertEqual(self.store.task(task["id"])["status"], "WAITING_APPROVAL")
        self.development.present(task["id"])
        self.development.offers["default"]["expires"] = 0
        await self.req("say", text="sí")
        self.development.present(task["id"])
        await self.req("say", text="Cuéntame otra cosa")
        await self.req("say", text="sí")
        self.assertEqual(self.store.task(task["id"])["status"], "WAITING_APPROVAL")
        with self.assertRaises(ArgosError):
            await self.req("approve", session="other", task_id=task["id"],
                           fingerprint=task["result"]["pending_plan"]["fingerprint"])

    async def test_multiple_pending_plans_need_explicit_selection_and_code_works(self):
        first, second = await self.plan(), await self.plan(target="new")
        self.development.present(second["id"])
        await self.req("say", text="sí")
        self.assertEqual(self.store.task(second["id"])["status"], "WAITING_APPROVAL")
        review = await self.req("approval.review", task_id=first["id"])
        self.assertEqual(review["data"]["plan"]["fingerprint"], first["result"]["pending_plan"]["fingerprint"])
        code = self.core.approval_dialog.challenges["default"]["code"]
        await self.req("say", text="aprueba " + code)
        self.assertEqual((await self.settled(first["id"]))["status"], "COMPLETED")
        self.assertEqual(self.store.task(second["id"])["status"], "WAITING_APPROVAL")

    async def test_no_writes_before_plan_approval(self):
        self.provider.before_plan = ("files.write", {"file": "bad.py", "content": "x=1", "expected_sha256": ""})
        response = await self.req("develop", text="change", target="new")
        task = await self.settled(response["task_id"])
        self.assertEqual(task["status"], "FAILED")
        self.assertFalse((Path(self.development.state(task["id"])["workspace"]) / "bad.py").exists())

    async def test_scope_rejects_host_reads_writes_commands_and_unplanned_checks(self):
        for name, args in [
            ("files.read", {"file": str(self.source / "src/argos/core.py")}),
            ("files.write", {"file": str(self.source / "bad.py"), "content": "x=1", "expected_sha256": ""}),
            ("commands.exec", {"argv_json": '["true"]', "cwd": str(self.source)}),
            ("development.check", {"index": "8"}),
            ("files.write", {"file": ".env", "content": "x=1", "expected_sha256": ""}),
        ]:
            with self.subTest(name=name, args=args):
                self.provider.attack = name, args
                task = await self.plan(target="new")
                await self.approve(task)
                done = await self.settled(task["id"])
                self.assertEqual(done["status"], "FAILED", done)
                self.assertNotIn(task["id"], self.development.grants)
        self.assertFalse((self.source / "bad.py").exists())
        self.adapter.check.assert_not_called()

    async def test_source_changed_candidate_and_wrong_fingerprint_invalidate_approval(self):
        task = await self.plan()
        with self.assertRaises(ArgosError):
            await self.req("approve", task_id=task["id"], fingerprint="wrong")
        (Path(self.development.state(task["id"])["workspace"]) / "external.py").write_text("x=3")
        with self.assertRaises(ArgosError):
            await self.approve(task)
        self.assertNotIn(task["id"], self.development.grants)

    async def test_conversation_and_status_remain_available_during_work(self):
        task = await self.plan()
        self.provider.release.clear()
        await self.approve(task)
        await asyncio.wait_for(self.provider.started.wait(), 1)
        response = await asyncio.wait_for(self.req("say", text="Podemos hablar de otra cosa"), 1)
        self.assertEqual(response["speech"], "Sí, podemos seguir hablando.")
        status = await self.req("say", text="¿Cómo va esa mejora?")
        self.assertEqual(status["data"][0]["status"], "RUNNING")
        self.assertIn("implementando", status["speech"])
        self.assertEqual(len(self.store.tasks("default")), 1)
        self.provider.release.set()
        await self.settled(task["id"])

    async def test_notification_waits_until_current_conversation_response(self):
        self.core.speech = Mock()
        task = await self.plan()
        self.provider.release.clear()
        await self.approve(task)
        await asyncio.wait_for(self.provider.started.wait(), 1)
        entered, finish = asyncio.Event(), asyncio.Event()
        async def talk(*args):
            entered.set()
            await finish.wait()
            return Decision("answer", speech="Aquí está tu respuesta.")
        self.provider.decide = talk
        request = asyncio.create_task(self.req("say", text="Cuéntame algo", speak=True))
        await entered.wait()
        self.core.speech.enqueue.reset_mock()
        self.provider.release.set()
        await self.settled(task["id"])
        self.core.speech.enqueue.assert_not_called()
        finish.set()
        await request
        self.assertEqual([c.args[0] for c in self.core.speech.enqueue.call_args_list],
                         ["Aquí está tu respuesta.", self.provider.final])

    async def test_failed_missing_or_stale_checks_never_announce_success(self):
        for mode in ("failed", "missing", "stale"):
            with self.subTest(mode=mode):
                self.provider.skip_checks = mode == "missing"
                self.provider.edit_after_checks = mode == "stale"
                self.adapter.check.return_value = {"argv": ["python3"], "exit_code": 1 if mode == "failed" else 0,
                                                  "output": "result", "verification": "command_failed" if mode == "failed" else "command_passed"}
                task = await self.plan(target="new")
                await self.approve(task)
                done = await self.settled(task["id"])
                self.assertEqual(done["status"], "FAILED", done)
                self.assertNotEqual(self.core.notifications[-1]["speech"], self.provider.final)

    async def test_unreviewed_candidate_is_blocked_even_when_model_claims_completion(self):
        self.provider.skip_review = True
        task = await self.plan()
        await self.approve(task)
        done = await self.settled(task["id"])
        self.assertEqual(done["status"], "BLOCKED")
        self.assertNotEqual(self.core.notifications[-1]["speech"], self.provider.final)

    async def test_cancel_and_restart_revoke_authority_without_replaying_effects(self):
        task = await self.plan()
        self.provider.release.clear()
        await self.approve(task)
        await self.provider.started.wait()
        await self.core.close()
        self.assertFalse(self.development.grants)
        self.assertEqual(self.store.task(task["id"])["status"], "INTERRUPTED")
        self.core = Core(self.store, self.provider, development=Development(self.store, self.adapter))
        self.development = self.core.development
        await self.core.start()
        await self.req("resume", task_id=task["id"])
        resumed = await self.settled(task["id"])
        self.assertEqual(resumed["status"], "WAITING_APPROVAL")
        self.assertFalse((Path(self.development.state(task["id"])["workspace"]) / "feature.py").exists())
        await self.req("cancel", task_id=task["id"])
        with self.assertRaises(ArgosError):
            await self.approve(resumed)

    async def test_self_target_is_actual_installation_not_selected_other_project(self):
        other = self.root / "other"
        other.mkdir()
        project = self.store.add_project("other", str(other))
        with patch.object(self.provider, "decide", wraps=self.provider.decide) as decide:
            response = await self.req("say", text="implementa la mejora en ti mismo", project=project["id"])
            decide.assert_not_called()
        task = await self.settled(response["task_id"])
        self.assertEqual(self.development.state(task["id"])["source"], str(self.source))
        self.assertIsNone(task["project"])
        self.assertEqual(self.provider.contexts[0]["identity"]["source_root"], str(self.source))
        self.assertFalse(self.provider.contexts[0]["identity"]["activation_available"])

    async def test_missing_project_answer_preserves_original_objective(self):
        response = await self.req("develop", text="Implementa el cálculo", target="project")
        self.assertEqual(self.store.task(response["task_id"])["status"], "WAITING_INPUT")
        await self.req("say", text="demo")
        task = await self.settled(response["task_id"])
        self.assertEqual(task["objective"], "Implementa el cálculo")
        self.assertEqual(task["status"], "WAITING_APPROVAL")

    def test_structured_decisions_cannot_approve_or_escape_general(self):
        for kind, args in (("develop", {"target": "self"}), ("task_status", {"task_id": "all"})):
            data = {"kind": kind, "speech": "", "agent": "", "capability": "", "arguments": args}
            self.assertEqual(validate_decision(data).kind, kind)
            with self.assertRaises(ArgosError):
                validate_decision(data, "engineering")
        with self.assertRaises(ArgosError):
            validate_decision({"kind": "develop", "speech": "", "agent": "", "capability": "",
                               "arguments": {"target": "self", "approved": True}})


class WorkspaceTests(unittest.IsolatedAsyncioTestCase):
    async def test_snapshot_excludes_private_files_links_and_git_without_touching_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            (source / "app.py").write_text("x=1")
            (source / ".env").write_text("private")
            (source / ".git").mkdir()
            (source / ".git/config").write_text("private")
            (source / "link").symlink_to(source / "app.py")
            adapter = LinuxDevelopmentWorkspace(root / "state", source)
            state = adapter.prepare("sample", str(source))
            candidate = Path(state["workspace"])
            self.assertEqual([p.name for p in candidate.iterdir()], ["app.py"])
            (candidate / "app.py").write_text("x=2")
            review = adapter.review(state)
            self.assertEqual(review["changed_files"], ["app.py"])
            self.assertEqual((source / "app.py").read_text(), "x=1")
            self.assertFalse(review["activated"])

    async def test_real_sandbox_runs_checks_without_host_home_network_audio_or_host_writes(self):
        if not shutil.which("bwrap"):
            self.skipTest("bubblewrap not installed")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            sentinel = root / "host.txt"
            sentinel.write_text("unchanged")
            adapter = LinuxDevelopmentWorkspace(root / "state", root / "source")
            state = adapter.prepare("sample", None)
            probe = await adapter.check(state, ["true"])
            if probe["exit_code"]:
                self.skipTest("bubblewrap namespaces unavailable: " + probe["output"][:200])
            code = ("from pathlib import Path; import socket; "
                    f"assert not Path({str(sentinel)!r}).exists(); "
                    "assert not Path('/run/user').exists(); assert not Path('/dev/snd').exists(); "
                    "assert not Path('/home/iago').exists(); "
                    "Path('candidate.txt').write_text('changed'); ")
            with socket.socket() as host:
                host.bind(("127.0.0.1", 0))
                host.listen()
                port = host.getsockname()[1]
                code += (f"s=socket.socket(); s.settimeout(1); assert s.connect_ex(('127.0.0.1', {port})) != 0; "
                         "print('OK')")
                result = await adapter.check(state, ["python3", "-c", code])
            self.assertEqual(result["verification"], "command_passed", result)
            self.assertEqual(sentinel.read_text(), "unchanged")
            self.assertEqual((Path(state["workspace"]) / "candidate.txt").read_text(), "changed")

    async def test_cancellation_reaps_actual_sandbox_before_returning(self):
        if not shutil.which("bwrap"):
            self.skipTest("bubblewrap not installed")
        with tempfile.TemporaryDirectory() as temp:
            adapter = LinuxDevelopmentWorkspace(Path(temp), Path(temp))
            state = adapter.prepare("sample", None)
            probe = await adapter.check(state, ["true"])
            if probe["exit_code"]:
                self.skipTest("bubblewrap namespaces unavailable")
            entered, processes = asyncio.Event(), []
            original = asyncio.create_subprocess_exec
            async def spawn(*args, **kwargs):
                process = await original(*args, **kwargs)
                processes.append(process)
                entered.set()
                return process
            with patch("argos.development_workspace.asyncio.create_subprocess_exec", spawn):
                task = asyncio.create_task(adapter.check(state, ["sleep", "60"]))
                await entered.wait()
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
            self.assertIsNotNone(processes[0].returncode)

    async def test_missing_sandbox_does_not_fall_back_to_host_commands(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            adapter = LinuxDevelopmentWorkspace(root, root)
            with patch("argos.development_workspace.shutil.which", return_value=None), \
                    patch("argos.development_workspace.asyncio.create_subprocess_exec", AsyncMock()) as spawn:
                with self.assertRaises(ArgosError):
                    await adapter.check({"workspace": temp}, ["true"])
                spawn.assert_not_called()
