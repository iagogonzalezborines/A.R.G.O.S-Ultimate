import asyncio
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

from argos.codex import Codex
from argos.core import Core
from argos.inference_config import read, write
from argos.models import ArgosError, Decision, EscalationNeeded
from argos.providers import OllamaInterpreter, validate_decision, local_schema
from argos.store import Store


class InferenceRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "notes.txt").write_text("Public fixture for local inspection.\n")
        self.store = Store(self.root / "state")
        self.project = self.store.add_project("fixture", self.root)
        self.local = OllamaInterpreter("fixture-local")
        self.local.decide = AsyncMock(return_value=Decision("answer", speech="Aquí estoy."))
        self.remote = type("Remote", (), {"name": "codex-test", "work": AsyncMock(), "close": AsyncMock()})()
        self.core = Core(self.store, self.local, escalation_provider=self.remote)
        await self.core.start()

    async def asyncTearDown(self):
        await self.core.close()
        self.store.close()
        self.temporary.cleanup()

    async def request(self, text, **kwargs):
        return await self.core.request({"method": "say", "text": text, "conversation": True,
                                        "request_id": uuid.uuid4().hex, **kwargs})

    async def settle(self, task_id):
        await asyncio.wait_for(self.core.queue.join(), 5)
        return self.store.task(task_id)

    async def test_chat_presence_and_status_never_use_remote(self):
        await self.request("Argos?")
        await self.request("qué estás haciendo")
        await self.request("¿Qué significa idempotencia?")
        self.assertEqual(self.local.decide.await_count, 2)
        self.remote.work.assert_not_called()
        self.assertFalse(self.store.tasks())

    async def test_missing_local_or_local_failure_has_no_remote_fallback(self):
        self.local.decide.side_effect = ArgosError("Local engine unavailable")
        with self.assertRaises(ArgosError):
            await self.request("Argos?")
        self.core.interpreter = None
        response = await self.request("Are you there?")
        self.assertEqual(response["kind"], "clarify")
        self.remote.work.assert_not_called()

    async def test_known_capability_executes_without_any_model(self):
        response = await self.request("información del sistema")
        self.assertEqual((await self.settle(response["task_id"]))["status"], "COMPLETED")
        self.local.decide.assert_not_called()
        self.remote.work.assert_not_called()

    async def test_local_multistep_task_does_not_escalate(self):
        self.local.decide.side_effect = [
            Decision("capability", agent="engineering", capability="files.read", arguments={"file": "notes.txt"}),
            Decision("answer", speech="El archivo contiene una nota pública."),
        ]
        response = await self.request("engineering: resume la nota", project="fixture")
        done = await self.settle(response["task_id"])
        self.assertEqual(done["status"], "COMPLETED", done)
        self.assertEqual(done["result"]["verification"], "inspection_only")
        self.assertEqual(self.local.decide.call_args.args[1]["previous_operations"][0]["capability"], "files.read")
        self.remote.work.assert_not_called()

    async def test_escalation_is_task_bound_and_carries_evidence_while_chat_stays_local(self):
        entered, release = asyncio.Event(), asyncio.Event()
        self.local.decide.side_effect = [
            Decision("capability", agent="engineering", capability="files.read", arguments={"file": "notes.txt"}),
            Decision("escalate", arguments={"reason": "La interacción entre componentes supera mi capacidad local de análisis."}),
            Decision("answer", speech="Podemos seguir hablando."),
        ]
        async def remote_work(task, context, execute, save_thread, progress):
            self.assertEqual(context["previous_operations"][0]["capability"], "files.read")
            self.assertIsNone(task["thread_id"])
            save_thread("remote-task-thread")
            entered.set()
            await release.wait()
            return {"kind": "result", "speech": "Inspección analizada.", "detail": "Basada en la lectura local."}
        self.remote.work.side_effect = remote_work
        response = await self.request("engineering: analiza componentes", project="fixture")
        try:
            await asyncio.wait_for(entered.wait(), 5)
            chat = await self.request("¿Seguimos hablando?")
            self.assertEqual(chat["speech"], "Podemos seguir hablando.")
            self.assertIsNone(chat["task_id"])
        finally:
            release.set()
        done = await self.settle(response["task_id"])
        self.assertEqual(done["status"], "COMPLETED")
        self.assertEqual(done["thread_id"], "remote-task-thread")
        events = self.store.events(done["id"])
        self.assertEqual(sum(e["kind"] == "PROVIDER_ESCALATED" for e in events), 1)
        self.assertEqual(sum(e["kind"] == "CAPABILITY_STARTED" for e in events), 1)
        self.assertEqual(self.store.setting("task.provider:" + done["id"])["route"], "escalated")
        self.remote.work.assert_awaited_once()

    async def test_escalation_without_local_inspection_is_blocked(self):
        self.local.decide.return_value = Decision("escalate", arguments={"reason": "Esto parece demasiado difícil para el modelo local."})
        result = await self.request("engineering: analiza componentes", project="fixture")
        self.assertEqual((await self.settle(result["task_id"]))["status"], "BLOCKED")
        self.remote.work.assert_not_called()

    async def test_effect_attempt_blocks_provider_switch_and_replay(self):
        async def local_work(task, context, execute, save_thread, progress):
            await execute("files.read", {"file": "notes.txt"})
            # A possibly interrupted write counts even without a result event.
            self.store.event(task["id"], "CAPABILITY_STARTED", {"capability": "files.write"})
            raise EscalationNeeded("La interacción entre componentes supera mi capacidad local de análisis.")
        self.local.work = local_work
        result = await self.request("engineering: analiza componentes", project="fixture")
        self.assertEqual((await self.settle(result["task_id"]))["status"], "BLOCKED")
        self.remote.work.assert_not_called()

    async def test_legacy_thread_cannot_be_resumed_on_local_provider(self):
        task = self.store.create_task("default", None, "engineering", "Old task")
        task = self.store.update(task["id"], "INTERRUPTED", thread_id="old-codex-thread")
        with self.assertRaises(ArgosError):
            self.core.task_provider(task)
        self.remote.work.assert_not_called()

    async def test_local_task_model_is_pinned_and_provider_handoff_clears_old_thread(self):
        task = self.store.create_task("default", None, "engineering", "Task")
        self.core.task_provider(task)
        self.local.model = "another-model"
        with self.assertRaises(ArgosError):
            self.core.task_provider(task)
        self.local.model = "fixture-local"
        self.store.update(task["id"], "RUNNING", thread_id="local-thread")
        route = {"route": "escalated", "provider": self.remote.name, "reason": "Needs deeper reasoning"}
        changed = self.store.handoff_provider(task["id"], route)
        self.assertIsNone(changed["thread_id"])
        self.assertEqual(changed["status"], "QUEUED")
        self.assertEqual(self.store.setting("task.provider:" + task["id"]), route)
        self.store.recover()
        self.assertEqual(self.store.task(task["id"])["status"], "INTERRUPTED")
        self.assertIs(self.core.task_provider(self.store.task(task["id"])), self.remote)
        self.remote.work.assert_not_called()

    async def test_launcher_reuses_existing_backend_without_starting_codex_or_another_engine(self):
        from argos.ollama_host import ensure
        with patch("argos.ollama_host.available", return_value=True), patch("argos.ollama_host.subprocess.Popen") as spawn:
            await ensure(self.root)
        spawn.assert_not_called()

    async def test_core_rejects_codex_as_conversation_provider(self):
        provider = Codex(self.root / "probe")
        with self.assertRaises(ArgosError):
            Core(self.store, provider)
        self.assertIsNone(provider.process)

    def test_configuration_is_per_installation_and_does_not_enable_cloud_models(self):
        office, home = self.root / "office", self.root / "home"
        write(office, "small-local:4b", True)
        write(home, "larger-local:8b", True)
        self.assertEqual(read(office)["ollama_model"], "small-local:4b")
        self.assertEqual(read(home)["ollama_model"], "larger-local:8b")
        with self.assertRaises(ArgosError):
            write(home, "some-model:cloud", True)

    def test_general_cannot_request_escalation(self):
        decision = {"kind": "escalate", "speech": "", "agent": "", "capability": "",
                    "arguments": {"reason": "La interacción entre componentes supera mi capacidad local."}}
        with self.assertRaises(ArgosError):
            validate_decision(decision)
        self.assertEqual(validate_decision(decision, "engineering").kind, "escalate")

    def test_local_schema_discriminates_conversation_before_tools_and_scopes_roles(self):
        capabilities = [
            {"name": "files.read", "agent": "engineering", "arguments": ["file"]},
            {"name": "web.search", "agent": "research", "arguments": ["query"]},
        ]
        schema = local_schema({"capabilities": capabilities, "previous_operations": [{"capability": "files.read"}]}, "computer")
        branches = schema["oneOf"]
        for branch in branches:
            self.assertEqual(sorted(branch["properties"])[0], "kind")
        answer = next(b for b in branches if b["properties"]["kind"]["const"] == "answer")["properties"]
        self.assertEqual(answer["target_agent"]["const"], "")
        self.assertEqual(answer["tool"]["const"], "")
        self.assertFalse(answer["tool_arguments"]["additionalProperties"])
        tools = [b["properties"]["tool"]["const"] for b in branches]
        self.assertIn("files.read", tools)
        self.assertNotIn("web.search", tools)
        self.assertFalse(any(b["properties"]["kind"]["const"] == "escalate" for b in branches))
        initial = local_schema({"capabilities": capabilities}, "computer")["oneOf"]
        self.assertNotIn("answer", [b["properties"]["kind"]["const"] for b in initial])
