import asyncio
import json
import struct
import tempfile
import time
import unittest
import uuid
from pathlib import Path

from argos.core import Core
from argos.models import ArgosError, Decision, Status
from argos.providers import validate_decision
from argos.store import Store


STL = b"""solid triangle
facet normal 0 0 1
outer loop
vertex 0 0 0
vertex 10 0 0
vertex 0 20 0
endloop
endfacet
endsolid triangle
"""


class CoreTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        (self.project / "part.stl").write_bytes(STL)
        (self.project / "part.gcode").write_text("G21\nM104 S200\nM140 S60\nG1 X10 Y20\n")
        self.store = Store(self.root / "state")
        self.store.add_project("Alpha", self.project)
        self.core = Core(self.store)
        await self.core.start()

    async def asyncTearDown(self):
        await self.core.close()
        self.store.close()
        self.tmp.cleanup()

    async def req(self, method="say", **kwargs):
        return await self.core.request({"method": method, "request_id": uuid.uuid4().hex, **kwargs})

    async def settled(self, task_id):
        await asyncio.wait_for(self.core.queue.join(), 3)
        return self.store.task(task_id)

    async def test_greeting_creates_no_task(self):
        result = await self.req(text="hola")
        self.assertEqual(result["speech"], "Hola.")
        self.assertEqual(self.store.tasks(), [])

    async def test_conversation_preparation_is_visible_without_blocking_commands(self):
        entered, release = asyncio.Event(), asyncio.Event()
        contexts = []
        class Provider:
            name = "test"
            async def prepare(self, context):
                contexts.append(context)
                entered.set()
                await release.wait()
        self.core.interpreter = Provider()
        await self.req("voice.prepare", project="Alpha")
        await asyncio.wait_for(entered.wait(), 1)
        await self.req("voice.prepare", project="Alpha")
        state = (await self.req("voice.state"))["data"]
        self.assertTrue(state["preparing"])
        self.assertEqual(state["state"], "thinking")
        self.assertEqual((await self.req(text="hola"))["speech"], "Hola.")
        release.set()
        await asyncio.gather(*self.core.preparations.values())
        state = (await self.req("voice.state"))["data"]
        self.assertFalse(state["preparing"])
        self.assertEqual(state["state"], "idle")
        self.assertEqual(len(contexts), 1)
        self.assertEqual(contexts[0]["project"]["name"], "Alpha")

    async def test_failed_preparation_can_be_retried_without_blocking_local_work(self):
        calls = []
        class Provider:
            name = "test"
            async def prepare(self, context):
                calls.append(context)
                if len(calls) == 1:
                    raise ArgosError("offline")
        self.core.interpreter = Provider()
        await self.req("voice.prepare")
        await asyncio.gather(*self.core.preparations.values())
        state = (await self.req("voice.state"))["data"]
        self.assertEqual(state["state"], "error")
        self.assertEqual((await self.req(text="hola"))["speech"], "Hola.")
        await self.req("voice.prepare")
        await asyncio.gather(*self.core.preparations.values())
        self.assertIsNone((await self.req("voice.state"))["data"]["error"])

    async def test_real_system_capability(self):
        response = await self.req("run", capability="system.info")
        self.assertEqual(response["data"]["status"], "QUEUED")
        task = await self.settled(response["task_id"])
        self.assertEqual(task["status"], "COMPLETED")
        self.assertIn("cpu_count", task["result"]["evidence"])

    async def test_real_git_repository_inspection(self):
        import subprocess
        subprocess.run(["git", "init", "-q", str(self.project)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        (self.project / "module.py").write_text("value = 42\n")
        subprocess.run(["git", "-C", str(self.project), "add", "module.py"], check=True)
        response = await self.req("run", capability="repo.inspect", project="Alpha")
        task = await self.settled(response["task_id"])
        self.assertEqual(task["status"], "COMPLETED")
        evidence = task["result"]["evidence"]
        self.assertTrue(evidence["git"])
        self.assertIn("module.py", evidence["tracked_changes"])
        self.assertNotIn("value = 42", json.dumps(task))

    async def test_real_stl_measurements(self):
        response = await self.req("run", capability="stl.inspect", project="Alpha", arguments={"file": "part.stl"})
        task = await self.settled(response["task_id"])
        self.assertEqual(task["result"]["evidence"]["dimensions"], [10, 20, 0])
        self.assertEqual(task["result"]["evidence"]["units"], "unspecified")
        self.assertEqual(task["status"], "COMPLETED")

    async def test_gcode_never_actuates_printer(self):
        response = await self.req("run", capability="gcode.inspect", project="Alpha", arguments={"file": "part.gcode"})
        task = await self.settled(response["task_id"])
        self.assertEqual(task["result"]["evidence"]["declared_tool_temperatures"], [200])
        self.assertIn("No se ha enviado", task["result"]["speech"])

    async def test_missing_project_answer_continues_same_task(self):
        result = await self.req(text="inspecciona el proyecto")
        task_id = result["task_id"]
        self.assertEqual(self.store.task(task_id)["status"], "WAITING_INPUT")
        await self.req(text="hola")
        await self.req(text="estado del pc")
        self.assertEqual(self.store.task(task_id)["status"], "WAITING_INPUT")
        answer = await self.req(text="Alpha")
        self.assertEqual(answer["task_id"], task_id)
        task = await self.settled(task_id)
        self.assertEqual(task["status"], "COMPLETED")
        self.assertEqual(len([t for t in self.store.tasks() if t["agent"] == "engineering"]), 1)

    async def test_unknown_project_stays_pending(self):
        result = await self.req(text="inspecciona el proyecto")
        answer = await self.req("reply", task_id=result["task_id"], text="Missing")
        self.assertEqual(answer["kind"], "clarify")
        self.assertEqual(self.store.task(result["task_id"])["status"], "WAITING_INPUT")

    async def test_ambiguous_pending_does_not_guess(self):
        await self.req(text="inspecciona el proyecto")
        await self.req(text="design3d: modela una pieza")
        answer = await self.req(text="Alpha")
        self.assertEqual(answer["kind"], "clarify")
        self.assertEqual(sum(t["status"] == "WAITING_INPUT" for t in self.store.tasks()), 2)

    async def test_session_cannot_answer_other_session_task(self):
        result = await self.req(text="inspecciona el proyecto", session="A")
        with self.assertRaises(ArgosError):
            await self.req("reply", task_id=result["task_id"], text="Alpha", session="B")

    async def test_unknown_language_is_not_executed(self):
        response = await self.req(text="No quiero que abras Firefox, solo explica cómo.")
        self.assertEqual(response["kind"], "clarify")
        self.assertFalse(self.store.tasks())

    async def test_missing_provider_never_claims_working(self):
        response = await self.req(text="corrige el importador", project="Alpha")
        self.assertEqual(response["kind"], "blocked")
        self.assertEqual(self.store.task(response["task_id"])["status"], "BLOCKED")

    async def test_update_does_not_restart_or_claim_installation(self):
        response = await self.req(text="actualiza argos")
        self.assertEqual(response["kind"], "blocked")
        self.assertIn("No se ha cambiado", response["speech"])

    async def test_idempotency_returns_same_task(self):
        request = {"method": "run", "request_id": "test-idempotency", "capability": "system.info"}
        first, second = await asyncio.gather(self.core.request(request), self.core.request(request))
        self.assertEqual(first, second)
        self.assertEqual(len(self.store.tasks()), 1)
        with self.assertRaises(ArgosError):
            await self.core.request({**request, "capability": "repo.inspect"})

    async def test_uncertain_request_is_not_replayed(self):
        message = {"method": "run", "request_id": "uncertain-request", "capability": "system.info"}
        import hashlib
        digest = hashlib.sha256(json.dumps(message, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.store.reserve(message["request_id"], digest)
        with self.assertRaises(ArgosError):
            await self.core.request(message)
        self.assertFalse(self.store.tasks())

    async def test_cancel_queued_does_not_execute(self):
        result = await self.req("run", capability="system.info")
        await self.req("cancel", task_id=result["task_id"])
        task = await self.settled(result["task_id"])
        self.assertEqual(task["status"], "CANCELLED")
        self.assertNotIn("CAPABILITY_STARTED", [e["kind"] for e in self.store.events(task["id"])])

    async def test_recovery_preserves_task_without_replay(self):
        task = self.store.create_task("default", None, "computer", "info", "system.info", status=Status.RUNNING)
        self.store.recover()
        self.assertEqual(self.store.task(task["id"])["status"], "INTERRUPTED")
        self.assertTrue(self.core.queue.empty())
        await self.req("resume", task_id=task["id"])
        self.assertEqual((await self.settled(task["id"]))["status"], "COMPLETED")

    async def test_voice_polling_does_not_write_database(self):
        before = self.store.db.total_changes
        for _ in range(20):
            await self.req("voice.state")
        self.assertEqual(self.store.db.total_changes, before)

    async def test_gaming_drops_notifications(self):
        await self.req(text="activa modo gaming")
        result = await self.req("run", capability="system.info")
        await self.settled(result["task_id"])
        self.assertFalse(self.core.notifications)
        await self.req(text="desactiva modo gaming")
        self.assertFalse(self.core.notifications)

    async def test_secret_never_persisted(self):
        secret = "sk-" + "x" * 32
        with self.assertRaises(ArgosError):
            await self.req(text=secret)
        dump = "\n".join(self.store.db.iterdump())
        self.assertNotIn(secret, dump)
        self.assertFalse(self.store.tasks())

    async def test_path_escape_rejected(self):
        result = await self.req("run", capability="stl.inspect", project="Alpha",
                                arguments={"file": "../project/part.stl"})
        self.assertEqual((await self.settled(result["task_id"]))["status"], "FAILED")

    async def test_symlink_rejected(self):
        (self.project / "linked.stl").symlink_to(self.project / "part.stl")
        result = await self.req("run", capability="stl.inspect", project="Alpha",
                                arguments={"file": "linked.stl"})
        self.assertEqual((await self.settled(result["task_id"]))["status"], "FAILED")

    async def test_project_context_isolation(self):
        another = self.root / "secret-project"
        another.mkdir()
        self.store.add_project("UnrelatedPrivateName", another)
        context = self.core.context(self.store.project("Alpha"), "engineering")
        self.assertNotIn("UnrelatedPrivateName", json.dumps(context))
        self.assertEqual(context["project"]["root"], str(self.project))
        self.assertNotIn(str(another), json.dumps(context))

    async def test_status_remains_responsive_during_provider_work(self):
        entered, release = asyncio.Event(), asyncio.Event()
        class Slow:
            name = "test"
            async def decide(self, text, context, agent="general"):
                entered.set()
                await release.wait()
                return Decision("clarify", speech="¿Qué parte?")
        self.core.interpreter = Slow()
        result = await self.req(text="corrige el importador", project="Alpha")
        await asyncio.wait_for(entered.wait(), 1)
        start = time.perf_counter()
        status = await self.req(text="estado")
        self.assertLess(time.perf_counter() - start, 0.1)
        self.assertEqual(status["data"][0]["status"], "RUNNING")
        release.set()
        self.assertEqual((await self.settled(result["task_id"]))["status"], "WAITING_INPUT")

    async def test_provider_question_resumes_same_task_with_answer(self):
        calls = []
        class Asking:
            name = "test"
            async def decide(self, text, context, agent="general"):
                calls.append(context)
                if len(calls) == 1:
                    return Decision("clarify", speech="¿Inspecciono Git?")
                return Decision("capability", agent="engineering", capability="repo.inspect")
        self.core.interpreter = Asking()
        response = await self.req(text="engineering: revisa", project="Alpha")
        task = await self.settled(response["task_id"])
        self.assertEqual(task["status"], "WAITING_INPUT")
        answer = await self.req("reply", task_id=task["id"], text="Sí, solo Git.")
        self.assertEqual(answer["task_id"], task["id"])
        self.assertEqual((await self.settled(task["id"]))["status"], "COMPLETED")
        self.assertEqual(calls[1]["task"]["answers"], ["Sí, solo Git."])

    async def test_provider_cannot_cross_specialist_boundary(self):
        class Wrong:
            name = "test"
            async def decide(self, *args):
                return Decision("capability", capability="gcode.inspect", arguments={"file": "part.gcode"})
        self.core.interpreter = Wrong()
        result = await self.req(text="engineering: revisa", project="Alpha")
        self.assertEqual((await self.settled(result["task_id"]))["status"], "FAILED")

    async def test_no_second_model_for_obvious_capability(self):
        class Never:
            name = "test"
            async def decide(self, *args):
                raise AssertionError("Unexpected model call")
        self.core.interpreter = Never()
        response = await self.req(text="estado del pc")
        self.assertEqual((await self.settled(response["task_id"]))["status"], "COMPLETED")

    async def test_provider_success_claim_is_not_reported(self):
        class Liar:
            name = "test"
            async def decide(self, *args):
                return Decision("answer", speech="He abierto Firefox.")
        self.core.interpreter = Liar()
        result = await self.req(text="abre mi navegador")
        self.assertIn("No se ha ejecutado", result["speech"])
        self.assertFalse(self.store.tasks())

    async def test_honest_execution_denials_preserve_the_model_response(self):
        class Honest:
            name = "test"
            speech = ""
            async def decide(self, *args):
                return Decision("answer", speech=self.speech)
        provider = Honest()
        self.core.interpreter = provider
        for speech in (
            "Todavía no. No he ejecutado ninguna comprobación del equipo ni recibido una imagen para revisarla.",
            "No estoy trabajando en eso; aún no hay una tarea.",
            "Tampoco lo he modificado.",
            "Nunca he enviado ese archivo.",
            "I'm not working on it; no task has been started.",
        ):
            with self.subTest(speech=speech):
                provider.speech = speech
                result = await self.req(text="¿Ya lo has comprobado?", conversation=True)
                self.assertEqual(result["speech"], speech)
                self.assertEqual(result["route"], "provider")
        self.assertFalse(self.store.tasks())

    async def test_denials_do_not_hide_another_unsupported_execution_claim(self):
        class Claim:
            name = "test"
            speech = ""
            async def decide(self, *args):
                return Decision("answer", speech=self.speech)
        provider = Claim()
        self.core.interpreter = provider
        for speech in (
            "No he abierto Firefox, pero he ejecutado las pruebas.",
            "No solo he abierto Firefox; también está listo.",
            "No, he terminado la tarea.",
            "No.\nHe modificado el archivo.",
            "I’m working on it.",
        ):
            with self.subTest(speech=speech):
                provider.speech = speech
                result = await self.req(text="¿Ya lo has comprobado?", conversation=True)
                self.assertIn("No se ha ejecutado", result["speech"])
                self.assertEqual(result["route"], "local")
        self.assertFalse(self.store.tasks())

    async def test_same_project_waiters_do_not_starve_other_work(self):
        entered, release = asyncio.Event(), asyncio.Event()
        class Slow:
            name = "test"
            async def decide(self, *args):
                entered.set()
                await release.wait()
                return Decision("clarify", speech="¿Qué archivo?")
        self.core.interpreter = Slow()
        await self.req(text="engineering: investiga A", project="Alpha")
        await self.req(text="engineering: investiga B", project="Alpha")
        await asyncio.wait_for(entered.wait(), 1)
        other = await self.req("run", capability="system.info")
        try:
            for _ in range(50):
                if self.store.task(other["task_id"])["status"] == "COMPLETED":
                    break
                await asyncio.sleep(0.01)
            self.assertEqual(self.store.task(other["task_id"])["status"], "COMPLETED")
        finally:
            release.set()
            await asyncio.wait_for(self.core.queue.join(), 3)

    async def test_task_cannot_complete_without_running(self):
        task = self.store.create_task("default", None, "computer", "info", "system.info")
        with self.assertRaises(ArgosError):
            self.store.update(task["id"], Status.COMPLETED, result={"speech": "done"})

    async def test_stopping_speech_does_not_cancel_task(self):
        entered, release = asyncio.Event(), asyncio.Event()
        class Slow:
            name = "test"
            async def decide(self, *args):
                entered.set()
                await release.wait()
                return Decision("clarify", speech="¿Qué archivo?")
        class Voice:
            stopped = False
            async def stop(self):
                self.stopped = True
        self.core.interpreter, self.core.voice = Slow(), Voice()
        result = await self.req(text="engineering: investiga", project="Alpha")
        await asyncio.wait_for(entered.wait(), 1)
        await self.req(text="deja de hablar")
        self.assertTrue(self.core.voice.stopped)
        self.assertEqual(self.store.task(result["task_id"])["status"], "RUNNING")
        release.set()
        await asyncio.wait_for(self.core.queue.join(), 3)
