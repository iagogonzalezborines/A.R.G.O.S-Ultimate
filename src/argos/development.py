"""Task-scoped development orchestration. Core retains all authority/evidence."""
import asyncio
import json
import time

from .models import ArgosError, Response, Status
from .security import fingerprint, public_text, safe_data


FILES = {"files.list", "files.list_page", "files.stat", "files.read", "files.read_range",
         "files.write", "files.patch", "files.mkdir", "files.copy", "files.move", "files.delete"}
READS = {"files.list", "files.list_page", "files.stat", "files.read", "files.read_range",
         "web.search", "web.read", "system.inspect"}
TOOLS = FILES | READS | {"development.plan", "development.check", "development.review"}


class PlanReady(ArgosError):
    pass


def capabilities(Capability):
    def handler(name):
        async def execute(project, args):
            if not project or "_development_executor" not in project:
                raise ArgosError("Esta capacidad requiere una tarea de desarrollo aislada.")
            return await project["_development_executor"](name, args)
        return execute
    return [Capability("development.plan", "engineering", "Proponer plan, explicación hablada y pruebas para una aprobación por tarea",
                       ("content",), True, handler("development.plan")),
            Capability("development.check", "engineering", "Ejecutar una prueba del plan aprobado en aislamiento",
                       ("index",), True, handler("development.check"), "execute"),
            Capability("development.review", "engineering", "Medir cambios y pruebas de la candidata sin activarla",
                       (), True, handler("development.review"))]


class Development:
    def __init__(self, store, workspace):
        self.store, self.workspace = store, workspace
        self.grants, self.offers = {}, {}

    def state(self, task_id):
        return self.store.setting("development:" + task_id)

    def save(self, task_id, state):
        self.store.set_setting("development:" + task_id, state)

    def create(self, task_id, source, target):
        self.save(task_id, {"source": source, "target": target, "phase": "preparing", "checks": {}})

    def revoke(self, task_id):
        self.grants.pop(task_id, None)
        self.offers = {k: v for k, v in self.offers.items() if v["task_id"] != task_id}

    def present(self, task_id):
        task = self.store.task(task_id)
        pending = (task["result"] or {}).get("pending_plan")
        if task["status"] == Status.WAITING_APPROVAL and pending:
            self.offers[task["session"]] = {"task_id": task_id, "fingerprint": pending["fingerprint"],
                                           "expires": time.monotonic() + 120}

    def confirmation(self, session, text, interrupted=False):
        from .router import normalize
        offer = self.offers.pop(session, None)  # any intervening turn disarms yes
        if not offer or interrupted or offer["expires"] < time.monotonic():
            return None
        waiting = [t for t in self.store.tasks(session) if t["status"] in (Status.WAITING_INPUT, Status.WAITING_APPROVAL)]
        if len(waiting) != 1 or waiting[0]["id"] != offer["task_id"]:
            return None
        if normalize(text) not in {"si", "si adelante", "adelante", "confirmo el plan", "yes", "yes go ahead",
                                   "go ahead", "confirm the plan"}:
            return None
        return {"method": "approve", "session": session, "task_id": offer["task_id"],
                "fingerprint": offer["fingerprint"]}

    async def approve(self, task, displayed):
        state = self.state(task["id"])
        pending = (task["result"] or {}).get("pending_plan")
        if not state or not pending or displayed != pending["fingerprint"] or state.get("plan") != pending:
            raise ArgosError("El plan ha cambiado; revísalo de nuevo.")
        review = await asyncio.to_thread(self.workspace.review, state)
        if review["candidate_sha256"] != pending["workspace_sha256"]:
            raise ArgosError("La copia cambió después del plan; cancela y prepara una tarea nueva.")
        self.grants[task["id"]] = displayed
        self.offers.pop(task["session"], None)
        state["phase"] = "implementing"
        self.save(task["id"], state)
        self.store.event(task["id"], "PLAN_APPROVED", {"fingerprint": displayed})

    def authorize(self, task, name, args):
        state = self.state(task["id"])
        if name not in TOOLS:
            raise ArgosError("Esa operación no pertenece al plan aislado. Requiere otra petición concreta.")
        self.workspace.scope(state, name, args)
        approved = bool(self.grants.get(task["id"])) and self.grants.get(task["id"]) == (state.get("plan") or {}).get("fingerprint")
        if name not in READS | {"development.plan", "development.review"} and not approved:
            raise ArgosError("Primero explica el plan con development.plan y espera la confirmación.")
        if name == "development.check":
            self.check_index(state, args)

    @staticmethod
    def check_index(state, args):
        index = args.get("index", "")
        if not index.isdecimal() or len(index) > 3 or int(index) >= len(state.get("plan", {}).get("checks", [])):
            raise ArgosError("La prueba no está incluida en el plan aprobado.")
        return int(index)

    async def execute(self, task, name, args):
        state = self.state(task["id"])
        if name == "development.plan":
            try:
                plan = json.loads(args["content"])
            except ValueError:
                raise ArgosError("El plan debe ser JSON válido.") from None
            if (not isinstance(plan, dict) or set(plan) != {"speech", "steps", "checks"}
                    or not isinstance(plan["speech"], str) or not plan["speech"].strip()
                    or len(plan["speech"]) > 4000 or not isinstance(plan["steps"], list)
                    or not 1 <= len(plan["steps"]) <= 12 or not all(isinstance(s, str) and 0 < len(s) <= 1000 for s in plan["steps"])
                    or not isinstance(plan["checks"], list) or len(plan["checks"]) > 8):
                raise ArgosError("El plan necesita speech, pasos concretos y una lista de pruebas.")
            for argv in plan["checks"]:
                if (not isinstance(argv, list) or not 1 <= len(argv) <= 50
                        or not all(isinstance(a, str) and a and len(a) <= 2000 and "\x00" not in a for a in argv)):
                    raise ArgosError("Cada prueba debe ser una lista de argumentos, sin variables de entorno privadas.")
            safe_data(plan)
            review = await asyncio.to_thread(self.workspace.review, state)
            plan.update(task_id=task["id"], source=state["source"], workspace=state["workspace"],
                        target=state["target"], base_sha256=state["base_sha256"],
                        workspace_sha256=review["candidate_sha256"],
                        scope="candidate files and listed isolated checks only; no publication or activation")
            plan["fingerprint"] = fingerprint("development.plan", plan, task["id"])
            self.revoke(task["id"])
            state.update(plan=plan, phase="awaiting_plan", checks={})
            self.save(task["id"], state)
            raise PlanReady("Plan preparado.")
        if name == "development.check":
            index = self.check_index(state, args)
            state["phase"] = "testing"
            self.save(task["id"], state)
            before = await asyncio.to_thread(self.workspace.review, state)
            result = await self.workspace.check(state, state["plan"]["checks"][index])
            after = await asyncio.to_thread(self.workspace.review, state)
            result["candidate_sha256"] = after["candidate_sha256"]
            result["unchanged_by_check"] = before["candidate_sha256"] == after["candidate_sha256"]
            state["checks"][str(index)] = {**result, "output": result.get("output", "")[:4000],
                                           "output_truncated": len(result.get("output", "")) > 4000}
            self.save(task["id"], state)
            return {"speech": "Prueba terminada.", "evidence": result, "verification": result["verification"]}
        review = await self.review(task, state)
        state["reviewed_sha256"] = review["candidate_sha256"]
        self.save(task["id"], state)
        return {"speech": "Candidata revisada.", "evidence": review, "verification": review["verification"]}

    async def review(self, task, state):
        review = await asyncio.to_thread(self.workspace.review, state)
        checks = list(state.get("checks", {}).values())
        expected = len(state.get("plan", {}).get("checks", []))
        failed = any(c["verification"] == "command_failed" for c in checks)
        verified = expected > 0 and len(checks) == expected and all(
            c["verification"] == "command_passed" and c["unchanged_by_check"]
            and c["candidate_sha256"] == review["candidate_sha256"] for c in checks)
        review.update(checks=checks, expected_checks=expected, verification=("command_failed" if failed else
                      "command_passed" if verified else "changes_not_tested"),
                      objective=task["objective"], source=state["source"],
                      next_step="Review candidate before applying or activating it; running ARGOS is unchanged.")
        return review

    async def run(self, core, task):
        task_id = task["id"]
        state = self.state(task_id)
        provider = core.task_provider(task)
        if not hasattr(provider, "work"):
            raise ArgosError("El desarrollo delegado requiere un proveedor con herramientas.")
        if state["target"] == "project" and not state["source"]:
            project = self.store.project(task["project"])
            if not project:
                raise ArgosError("Falta seleccionar el proyecto de desarrollo.")
            state["source"] = project["root"]
        if "workspace" not in state:
            # A cancelled snapshot is allowed to finish its local copy only. It
            # never executes code; await it before relinquishing task ownership.
            job = asyncio.create_task(asyncio.to_thread(self.workspace.prepare, task_id, state["source"]))
            try:
                state.update(await asyncio.shield(job))
            except asyncio.CancelledError:
                state.update(await job)
                self.save(task_id, state)
                raise
            self.save(task_id, state)
        approved = task_id in self.grants
        state["phase"] = "implementing" if approved else "planning"
        self.save(task_id, state)
        project = {"id": task["project"] or task_id, "name": state["target"], "root": state["workspace"]}
        async def adapter(name, args):
            return await self.execute(task, name, args)
        project["_development_executor"] = adapter
        context = core.context(project, "engineering")
        context["capabilities"] = [c for c in context["capabilities"] if c["name"] in TOOLS]
        context["development"] = {**state, "authorized": approved}
        context["escalation"] = {"allowed": provider is core.interpreter and bool(core.escalation_provider) and not approved,
                                 "assignment": core.store.setting("task.provider:" + task_id)}
        context["scope"] = "Only this candidate's files and the approved isolated checks; no host mutations or activation."
        context["filesystem"] = {"root": state["workspace"], "absolute_paths": "inside candidate only"}
        context["task"] = {"id": task_id, "objective": task["objective"], "answers": [
            e["data"]["answer"] for e in reversed(self.store.events(task_id)) if e["kind"] == "USER_ANSWER"][-8:]}
        def conversation():
            key = (task["session"], task["project"])
            return self.store.recent_messages(core.conversation_ids.get(key), *key)
        context["recent_conversation"] = conversation()
        context["previous_operations"] = [e["data"] for e in reversed(self.store.events(task_id))
                                          if e["kind"] == "CAPABILITY_RESULT"][-12:]
        async def execute(name, args):
            result = await core.execute_capability(task, project, name, args, development_scope=True)
            if name == "development.review":
                result = {**result, "conversation": {
                    "turn_in_progress": bool(core.conversing),
                    "dialogue_open": bool(core.wake and core.wake.dialogue_open),
                    "recent_turns": conversation()}}
            return result
        def save_thread(thread):
            self.store.update(task_id, Status.RUNNING, thread_id=thread)
        def progress(text):
            public_text(text, 4000)
            self.store.event(task_id, "PROGRESS", {"summary": text})
        try:
            result = await provider.work(task, context, execute, save_thread, progress)
        except PlanReady:
            state = self.state(task_id)
            plan = state["plan"]
            self.store.update(task_id, Status.WAITING_APPROVAL,
                              result={"pending_plan": plan}, question=plan["speech"])
            core._notify(task_id, plan["speech"], on_spoken=lambda: self.present(task_id))
            return
        if result.get("kind") == "question":
            self.store.update(task_id, Status.WAITING_INPUT, question=result["speech"])
            core._notify(task_id, result["speech"])
            return
        state = self.state(task_id)
        review = await self.review(task, state)
        if not approved or not review["changed_count"] or state.get("reviewed_sha256") != review["candidate_sha256"]:
            self.revoke(task_id)
            self.store.update(task_id, Status.BLOCKED, result={**review, "provider_proposal": result},
                              question="No hay una candidata modificada y revisada bajo un plan aprobado.")
            core._notify(task_id, self.store.task(task_id)["question"])
            return
        failed = review["verification"] == "command_failed"
        missing = review["expected_checks"] > 0 and review["verification"] != "command_passed"
        # Failed/missing agreed checks cannot be promoted by model prose.
        speech = result["speech"]
        if failed or missing:
            speech = ("The candidate is prepared, but the agreed checks failed or remain unverified. "
                      "It has not been activated. The task details contain the results." if core.language() == "en" else
                      "La candidata está preparada, pero las pruebas acordadas fallaron o no están verificadas. "
                      "No se ha activado. Consulta el detalle de la tarea.")
        state["phase"] = "candidate_ready" if not (failed or missing) else "verification_failed"
        self.save(task_id, state)
        self.revoke(task_id)
        self.store.update(task_id, Status.FAILED if failed or missing else Status.COMPLETED,
                          result={**review, "speech": speech, "detail": result["detail"]})
        core._notify(task_id, speech)
