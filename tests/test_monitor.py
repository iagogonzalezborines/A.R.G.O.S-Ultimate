import asyncio
import json
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from argos.core import Core
from argos.models import ArgosError, Decision
from argos.monitor import clean, render_map, render_tasks
from argos.panels import Panels
from argos.providers import validate_decision
from argos.router import Router
from argos.store import Store


class MonitorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)
        self.store = Store(self.path / "state")
        self.core = Core(self.store)
        await self.core.start()

    async def asyncTearDown(self):
        await self.core.close()
        self.store.close()
        self.temp.cleanup()

    async def request(self, method="monitor.snapshot", **kwargs):
        return await self.core.request({"method": method, "request_id": uuid.uuid4().hex, **kwargs})

    async def test_map_counts_running_waiting_and_queued_without_poll_writes(self):
        running = self.store.create_task("default", None, "computer", "Abrir aplicación")
        self.store.update(running["id"], "RUNNING")
        self.store.create_task("default", None, "engineering", "Corregir pruebas")
        self.store.create_task("default", None, "research", "Investigar", status="WAITING_INPUT", question="¿Tema?")
        self.store.create_task("another-session", None, "computer", "Invisible")
        changes = self.store.db.total_changes
        data = (await self.request())["data"]
        self.assertEqual(self.store.db.total_changes, changes)
        self.assertEqual(data["counts"], {"running": 1, "queued": 1, "waiting": 1})
        agents = {a["id"]: a for a in data["agents"]}
        self.assertEqual(agents["computer"]["state"], "running")
        self.assertEqual(agents["computer"]["activity"], "Abrir aplicación")
        self.assertEqual(agents["research"]["state"], "waiting")
        self.assertEqual(agents["engineering"]["state"], "queued")
        self.assertEqual(len(agents), 6)
        self.assertEqual(agents["general"]["connection"], "not_configured")

    async def test_history_pages_are_complete_and_session_scoped(self):
        for index in range(109):
            task = self.store.create_task("default", None, "computer", f"Task {index}")
            self.store.update(task["id"], "CANCELLED")
        other = self.store.create_task("private-session", None, "computer", "Separate")
        ids = []
        for offset in range(0, 109, 24):
            page = (await self.request(filter="finished", offset=offset))["data"]
            self.assertEqual(page["total"], 109)
            ids.extend(row["id"] for row in page["rows"])
        self.assertEqual(len(set(ids)), 109)
        with self.assertRaises(ArgosError):
            await self.request("monitor.detail", kind="tasks", id=other["id"])
        with self.assertRaises(ArgosError):
            await self.request(offset=-1)

    async def test_task_timeline_includes_public_conversation_and_outcome(self):
        task = self.store.create_task("default", None, "engineering", "Objetivo")
        self.store.update(task["id"], "RUNNING", thread_id="thread-real")
        self.store.event(task["id"], "PROGRESS", {"summary": "Estoy revisando el archivo."})
        self.store.event(task["id"], "USER_ANSWER", {"answer": "Utiliza ese proyecto."})
        self.store.event(task["id"], "CAPABILITY_RESULT",
                         {"capability": "files.read", "result": {"speech": "He leído el archivo.", "evidence": "PRIVATE_TOOL_BODY"}})
        self.store.update(task["id"], "COMPLETED", result={"speech": "Terminado.", "detail": "Comprobación completa."})
        data = (await self.request("monitor.detail", id=task["id"]))["data"]
        text = json.dumps(data, ensure_ascii=False)
        self.assertIn("thread-real", text)
        self.assertIn("Comprobación completa.", text)
        self.assertIn("Utiliza ese proyecto.", text)
        self.assertNotIn("PRIVATE_TOOL_BODY", text)
        self.assertEqual(data["messages"][2]["role"], "ARGOS")

    async def test_record_history_has_pages_without_losing_old_messages(self):
        identifier = self.store.begin_conversation(None, "default", None, "test", "Primera pregunta")
        for index in range(30):
            self.store.finish_conversation(identifier, f"Respuesta {index}")
        contents = []
        for page in (0, 12, 24):
            data = (await self.request("monitor.detail", kind="conversations", id=identifier, offset=page))["data"]
            self.assertEqual(data["total"], 31)
            contents.extend(m["content"] for m in data["messages"])
        self.assertEqual(len(set(contents)), 31)
        self.assertIn("Primera pregunta", contents)

    async def test_general_is_busy_during_real_dispatch_and_keeps_public_history(self):
        entered, release = asyncio.Event(), asyncio.Event()
        class Provider:
            name = "test"
            async def decide(self, text, context):
                entered.set()
                await release.wait()
                return Decision("answer", speech="Una respuesta completa.")
            def conversation_thread(self, context):
                return "general-thread"
        self.core.interpreter = Provider()
        job = asyncio.create_task(self.request("say", text="Explícame una carpeta"))
        await entered.wait()
        data = (await self.request(kind="conversations"))["data"]
        self.assertEqual(data["agents"][0]["state"], "running")
        self.assertEqual(data["rows"][0]["thread_id"], "general-thread")
        release.set()
        await job
        identifier = data["rows"][0]["id"]
        data = (await self.request("monitor.detail", kind="conversations", id=identifier))["data"]
        self.assertEqual(data["status"], "IDLE")
        self.assertEqual([m["role"] for m in data["messages"]], ["user", "assistant"])
        self.assertEqual(data["messages"][-1]["content"], "Una respuesta completa.")
        await self.request("say", text="Explícame un archivo")
        self.assertEqual((await self.request(kind="conversations"))["data"]["total"], 1)
        self.core.conversation_ids.clear()
        self.assertEqual(self.store.db.execute("SELECT thread_id FROM conversations WHERE id=?", (identifier,)).fetchone()[0],
                         "general-thread")

    async def test_cancelled_general_turn_is_not_left_busy_or_replayed(self):
        entered = asyncio.Event()
        class Provider:
            name = "test"
            async def decide(self, text, context):
                entered.set()
                await asyncio.sleep(60)
        self.core.interpreter = Provider()
        job = asyncio.create_task(self.request("say", text="Explica un concepto"))
        await entered.wait()
        job.cancel()
        await asyncio.gather(job, return_exceptions=True)
        data = (await self.request(kind="conversations"))["data"]
        self.assertEqual(data["rows"][0]["status"], "INTERRUPTED")
        self.assertEqual(data["agents"][0]["running"], 0)

    async def test_panel_voice_routing_is_idempotent_and_never_calls_model(self):
        self.core.panels = SimpleNamespace(open=AsyncMock(return_value={"status": "requested"}))
        request = {"method": "say", "text": "Argos, muéstrame a los agentes", "request_id": uuid.uuid4().hex}
        first = await self.core.request(request)
        self.assertEqual(await self.core.request(request), first)
        self.core.panels.open.assert_awaited_once_with("agents", "default")
        self.assertIsNone(first["task_id"])

    async def test_natural_panel_request_uses_one_interpretation_and_records_actual_result(self):
        self.core.panels = SimpleNamespace(open=AsyncMock(return_value={"status": "requested", "view": "agents"}))
        decision = validate_decision({"kind": "panel", "speech": "MODEL_CLAIM",
                                      "agent": "", "capability": "", "arguments": {"view": "agents"}})
        self.core.interpreter = SimpleNamespace(name="test", decide=AsyncMock(return_value=decision))
        request = {"method": "say", "text": "I'd like a live view of which ARGOS agents are working.",
                   "request_id": uuid.uuid4().hex}
        result = await self.core.request(request)
        self.assertEqual(result["data"]["view"], "agents")
        self.assertNotIn("MODEL_CLAIM", result["speech"])
        self.assertEqual(await self.core.request(request), result)
        self.core.panels.open.assert_awaited_once_with("agents", "default")
        self.core.interpreter.decide.assert_awaited_once()
        context = self.core.interpreter.decide.call_args.args[1]
        self.assertEqual(context["panels"], ["agents", "tasks"])
        self.assertEqual(self.core.context(None, "engineering")["panels"], [])
        self.assertEqual(self.store.tasks("default"), [])
        messages = self.store.db.execute("SELECT content FROM messages WHERE role='assistant'").fetchall()
        self.assertEqual(len(messages), 1)
        self.assertNotIn("MODEL_CLAIM", messages[0]["content"])

    async def test_model_panel_request_cannot_claim_success_when_launcher_is_absent(self):
        self.core.interpreter = SimpleNamespace(name="test", decide=AsyncMock(
            return_value=Decision("panel", arguments={"view": "agents"})))
        self.assertEqual(self.core.context(None)["panels"], [])
        with self.assertRaises(ArgosError):
            await self.request("say", text="I'd like a live view of which ARGOS agents are working.")
        self.assertEqual(self.store.db.execute("SELECT status FROM conversations").fetchone()[0], "FAILED")

    async def test_diagram_and_task_views_fit_resize_and_sanitize_control_text(self):
        data = (await self.request())["data"]
        for width, height in ((128, 42), (80, 24), (50, 16)):
            canvas = render_map(data, width, height)
            self.assertEqual(len(canvas.cells), height)
            self.assertTrue(all(len(row) == width for row in canvas.cells))
            if width >= 76:
                for agent in data["agents"]:
                    self.assertIn(agent["name"], canvas.text())
                self.assertIn("ORQUESTADOR", canvas.text())
                self.assertIn("│", canvas.text())
        detail = {"id": "id", "title": "\x1b[2Jtitle", "thread_id": None, "messages": []}
        output = render_tasks(data, detail, 100, 32).text()
        self.assertNotIn("\x1b", output)
        self.assertNotIn("\x1b", clean("\x1b]52;c;test\x07"))

    async def test_v1_migration_preserves_history_and_marks_interrupted_chats(self):
        task = self.store.create_task("default", None, "computer", "Historial")
        self.store.update(task["id"], "CANCELLED")
        self.store.db.executescript("DROP TABLE messages; DROP TABLE conversations; PRAGMA user_version=1;")
        self.store.close()
        self.store = Store(self.path / "state")
        self.core.store = self.store
        self.assertEqual(self.store.task(task["id"])["status"], "CANCELLED")
        identifier = self.store.begin_conversation(None, "default", None, "test", "Hola")
        self.store.recover()
        self.assertEqual(self.store.db.execute("SELECT status FROM conversations WHERE id=?", (identifier,)).fetchone()[0],
                         "INTERRUPTED")
        self.assertEqual(self.store.db.execute("PRAGMA user_version").fetchone()[0], 2)


class PanelTests(unittest.IsolatedAsyncioTestCase):
    async def test_compositor_dispatch_supports_lua_and_legacy_without_active_window_targets(self):
        with tempfile.TemporaryDirectory() as temp:
            panels = Panels(Path(temp))
            with patch("argos.panels.process", AsyncMock(return_value=(0, "ok", ""))) as dispatch:
                self.assertTrue(await panels.dispatch("focus", "0x123"))
                self.assertIn('window="address:0x123"', dispatch.call_args.args[0][-1])
                self.assertEqual(dispatch.await_count, 1)
            with patch("argos.panels.process", AsyncMock(side_effect=[(1, "", ""), (0, "ok", "")])) as dispatch:
                self.assertTrue(await panels.dispatch("resize", "0x123", 1100, 700))
                self.assertEqual(dispatch.call_args.args[0][-1], "exact 1100 700,address:0x123")
            with patch("argos.panels.process", AsyncMock()) as dispatch:
                with self.assertRaises(ArgosError):
                    await panels.dispatch("focus", '0x123"}); unexpected()')
                dispatch.assert_not_called()

    async def test_repeated_open_launches_only_one_window_and_uses_argv(self):
        with tempfile.TemporaryDirectory() as temp:
            panels = Panels(Path(temp))
            with patch("argos.panels.shutil.which", side_effect=lambda name: "/usr/bin/kitty" if name == "kitty" else None), \
                 patch("argos.panels.subprocess.Popen", return_value=SimpleNamespace(poll=Mock(return_value=None))) as spawn, \
                 patch("argos.panels.asyncio.sleep", AsyncMock()):
                await panels.open("agents", "default")
                await panels.open("agents", "default")
                self.assertEqual(spawn.call_count, 1)
                self.assertIn("monitor", spawn.call_args.args[0])
                self.assertIn("agents", spawn.call_args.args[0])

    async def test_existing_panel_is_focused_and_brought_above_other_windows(self):
        with tempfile.TemporaryDirectory() as temp:
            panels = Panels(Path(temp))
            import hashlib
            identity = hashlib.sha256((str(Path(temp).resolve()) + ":default").encode()).hexdigest()[:10]
            window = {"class": f"argos-agents-{identity}", "address": "0x123"}
            with patch.object(panels, "windows", AsyncMock(return_value=[window])), \
                 patch("argos.panels.process", AsyncMock(return_value=(0, "ok", ""))) as dispatch, \
                 patch("argos.panels.subprocess.Popen") as spawn:
                result = await panels.open("agents", "default")
                self.assertEqual(result["status"], "focused")
                commands = [call.args[0][-1] for call in dispatch.await_args_list]
                self.assertEqual(commands, ['hl.dsp.focus({window="address:0x123"})',
                                           'hl.dsp.window.alter_zorder({window="address:0x123",mode="top"})'])
                spawn.assert_not_called()

    def test_exact_voice_variants_and_negated_or_quoted_non_actions(self):
        router = Router()
        for text in ("Argos muéstrame a los agentes", "el mapa de agentes", "diagrama de agentes",
                     "abre el mapa cerebral de agentes", "show me the agent map",
                     "The ARGOS agent diagram here.", "ARGOS, show me the map of agents.",
                     "¿Puedes abrir el mapa de los agentes?", "Ábreme el diagrama de agentes",
                     "Quiero ver el mapa de agentes", "Could you show me the ARGOS agent diagram, please?"):
            self.assertEqual(router.resolve(text).arguments, {"view": "agents"}, text)
        for text in ("abre el monitor de tareas", "historial de tareas", "muestra las conversaciones de codex",
                     "open the task monitor"):
            self.assertEqual(router.resolve(text).arguments, {"view": "tasks"}, text)
        for text in ('no muestres el mapa de agentes', '"abre el mapa de agentes"', 'si digo mapa de agentes qué pasa',
                     'ARGOS, show me the map of people.', 'What is an agent diagram?',
                     'Do not open the agent diagram', 'Could you explain the agent diagram?'):
            self.assertEqual(router.resolve(text).kind, "interpret", text)
