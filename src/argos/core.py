import asyncio
import hashlib
import json
import time
from collections import deque

from .agents import AGENTS, catalogue, contract
from .capabilities import CAPABILITIES
from .models import ArgosError, Decision, Response, Status, TERMINAL
from .policy import Operation, Policy, ApprovalNeeded
from .router import Router
from .security import public_text, safe_data
from .store import Store


class Core:
    def __init__(self, store: Store, interpreter=None, workers=2):
        self.store, self.interpreter = store, interpreter
        self.router, self.policy = Router(), Policy()
        self.queue = asyncio.Queue(maxsize=64)
        self.worker_count = workers
        self.workers, self.active, self.inflight = [], {}, {}
        self.dispatches = set()
        self.execution_slots = asyncio.Semaphore(workers)
        self.resource_locks = {}
        self.session_locks = {}
        self.notifications = deque(maxlen=32)
        self.voice = None
        self.speech = None
        self.capture = None
        self.closing = False

    async def start(self):
        self.store.recover()
        self.workers = [asyncio.create_task(self._worker()) for _ in range(self.worker_count)]

    async def close(self):
        self.closing = True
        for worker in self.workers:
            worker.cancel()
        await asyncio.gather(*self.workers, return_exceptions=True)
        for job in list(self.dispatches):
            job.cancel()
        await asyncio.gather(*self.dispatches, return_exceptions=True)
        # Graceful shutdown and crashes have the same conservative recovery rule.
        self.store.recover()
        if self.interpreter and hasattr(self.interpreter, "close"):
            await self.interpreter.close()

    def context(self, project, agent="general"):
        return {
            "project": {"id": project["id"], "name": project["name"]} if project else None,
            "capabilities": [c.public() for c in CAPABILITIES.values()
                             if agent == "general" or c.name in AGENTS[agent].capabilities],
            "agents": catalogue(self.interpreter.name if self.interpreter else "none"),
            "scope": "No source files, credentials, other project tasks or raw logs are supplied.",
        }

    async def request(self, message):
        safe_data(message)
        if not isinstance(message, dict):
            raise ArgosError("Petición inválida.")
        if message.get("method") in ("projects.list", "agents", "tasks", "task", "voice.state"):
            # Observation has no effects. Never persist audio meter samples or
            # issue SQLite writes for console/status polling.
            return (await self._dispatch(message)).json()
        key = message.get("request_id")
        if not isinstance(key, str) or not 8 <= len(key) <= 100:
            raise ArgosError("La petición necesita un identificador estable de 8–100 caracteres.")
        digest = hashlib.sha256(json.dumps(
            message, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if key in self.inflight:
            old_digest, future = self.inflight[key]
            if digest != old_digest:
                raise ArgosError("Identificador reutilizado con otra petición.")
            return await asyncio.shield(future)
        cached = self.store.cached(key, digest)
        if cached is not None:
            return cached
        self.store.reserve(key, digest)
        future = asyncio.get_running_loop().create_future()
        self.inflight[key] = digest, future
        try:
            response = await self._dispatch(message)
            data = response.json()
            self.store.cache(key, digest, data)
            if message.get("speak") and self.speech and response.speech:
                self.speech.enqueue(response.speech)
            future.set_result(data)
            return data
        except BaseException as exc:
            # Awaiters get the same failure; retrieve it locally to avoid warnings.
            future.set_exception(exc)
            future.exception()
            raise
        finally:
            self.inflight.pop(key, None)

    async def _dispatch(self, request):
        method = request.get("method", "say")
        session = request.get("session", "default")
        public_text(session, 100)
        if method == "projects.add":
            project = self.store.add_project(request["name"], request["path"])
            return Response(f"Proyecto {project['name']} registrado.", data=project)
        if method == "commands.register":
            project = self.store.project(request["project"])
            if project is None:
                raise ArgosError("Selecciona un proyecto.")
            argv = request.get("argv")
            if not isinstance(argv, list) or not argv or not all(isinstance(x, str) for x in argv):
                raise ArgosError("El comando necesita una lista de argumentos.")
            if not request.get("name") or len(argv) > 50:
                raise ArgosError("Definición de comando inválida.")
            public_text(request["name"], 80)
            if argv[0].startswith("-") or any("\x00" in x or len(x) > 4000 for x in argv):
                raise ArgosError("Argumentos de comando inválidos.")
            import shutil
            resolved = shutil.which(argv[0])
            if not resolved:
                raise ArgosError("No se encuentra el ejecutable del comando.")
            spec = {"argv": [resolved, *argv[1:]]}
            key = "commands:" + project["id"]
            commands = self.store.setting(key, {})
            commands[request["name"]] = spec
            self.store.set_setting(key, commands)
            return Response("Comando registrado. Su ejecución pedirá aprobación.", data={
                "command": request["name"], "expected_sha256":
                hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()})
        if method == "projects.list":
            return self._local(Decision("projects"), session)
        if method == "agents":
            return self._local(Decision("agents"), session)
        if method == "tasks":
            return self._local(Decision("status"), session)
        if method == "run":
            cap = CAPABILITIES.get(request.get("capability"))
            if not cap:
                raise ArgosError("Capacidad desconocida.")
            project = self.store.project(request.get("project"))
            return self._decision(Decision("capability", agent=cap.agent, capability=cap.name,
                                           arguments=request.get("arguments", {})),
                                  cap.description, project, session)
        if method == "task":
            task = self.store.task(request["task_id"])
            return Response(self.describe(task), data={**task, "events": self.store.events(task["id"])})
        if method in ("cancel", "resume", "reply", "approve"):
            task = self.store.task(request["task_id"])
            if task["session"] != session:
                raise ArgosError("La tarea pertenece a otra sesión.")
            if method == "approve":
                if task["status"] != Status.WAITING_APPROVAL:
                    raise ArgosError("La tarea no espera aprobación.")
                pending = (task["result"] or {}).get("pending_operation")
                if not pending:
                    raise ArgosError("No hay una operación revisable.")
                operation = self.operation(task["id"], pending["capability"],
                                           pending["arguments"], task["project"])
                self.policy.approve(operation, request.get("fingerprint", ""))
                self.store.event(task["id"], "APPROVED", pending)
                self._enqueue(task)
                return Response("Aprobación recibida. Continúo la misma tarea.", "accepted", task["id"])
            if method == "cancel":
                if task["status"] in TERMINAL:
                    return Response("La tarea ya terminó.", task_id=task["id"])
                job = self.active.get(task["id"])
                if job:
                    job.cancel()
                    await asyncio.gather(job, return_exceptions=True)
                self.store.update(task["id"], Status.CANCELLED)
                return Response("Tarea cancelada.", task_id=task["id"])
            if method == "resume":
                if task["status"] != Status.INTERRUPTED:
                    raise ArgosError("Solo se reanudan aquí tareas interrumpidas y revisadas.")
                self._enqueue(task)
                return Response("Tarea reanudada en la cola.", task_id=task["id"])
            return await self._answer(task, public_text(request.get("text", "")))
        if method == "voice.state":
            data = self.voice.snapshot() if self.voice else {"state": "idle", "level": 0}
            if self.capture and self.capture.state != "idle":
                data = {**data, "state": self.capture.state}
            elif self.speech and self.speech.state != "idle" and data["state"] != "speaking":
                data = {**data, "state": self.speech.state}
            data["stt"] = "whisper-base" if self.capture else "not_connected"
            data["tts"] = "pocket-peter-yearsley" if self.speech else "not_connected"
            data["error"] = ((self.capture.last_error if self.capture else None)
                             or (self.speech.last_error if self.speech else None))
            return Response("", data=data)
        if method == "voice.toggle":
            if not self.capture:
                raise ArgosError("El micrófono no está conectado.")
            await self.capture.toggle(request.get("project"))
            return Response("")
        if method == "voice.play":
            if self.voice is None:
                raise ArgosError("No hay salida de audio conectada.")
            await self.voice.play(request["path"])
            return Response("Reproducción iniciada.")
        if method == "voice.stop":
            if self.capture:
                await self.capture.cancel()
            if self.speech:
                await self.speech.stop()
            if self.voice:
                await self.voice.stop()
            return Response("Audio detenido.")
        if method != "say":
            raise ArgosError("Operación de Core desconocida.")
        text = public_text(request.get("text", "")).strip()
        if not text:
            raise ArgosError("La petición está vacía.")
        project = self.store.project(request.get("project"))
        decision = self.router.resolve(text)
        if decision.kind in ("greeting", "status", "capabilities", "agents", "projects",
                             "gaming_on", "gaming_off"):
            return self._local(decision, session)
        if decision.kind == "stop_speech":
            if self.speech:
                await self.speech.stop()
            if self.voice:
                await self.voice.stop()
            return Response("De acuerdo.")
        if decision.kind == "maintenance":
            task = self.store.create_task(
                session, project["id"] if project else None, "engineering", text,
                status=Status.BLOCKED,
                question="El instalador de actualizaciones aún no está conectado. No se ha cambiado ni reiniciado ARGOS.")
            return Response(task["question"], "blocked", task["id"])
        if decision.kind == "interpret":
            pending = [t for t in self.store.tasks(session)
                       if t["status"] == Status.WAITING_INPUT
                       and (not project or t["project"] in (None, project["id"]))]
            # Only an explicit project answer or reply marker binds implicitly.
            # New conversation must never be swallowed by task focus.
            if pending:
                matches = [p for p in self.store.projects() if p["name"].casefold() == text.casefold()]
                explicit_reply = text.casefold().startswith(("respuesta:", "answer:"))
                if matches or explicit_reply:
                    if len(pending) != 1:
                        return Response("Hay varias preguntas pendientes. Indica la tarea al responder.", "clarify")
                    return await self._answer(pending[0], text.split(":", 1)[-1].strip() if explicit_reply else text)
            if not self.interpreter:
                return Response(
                    "No he podido resolver esa petición localmente. La interpretación por IA aún no está configurada.",
                    "clarify", data={"available": [c.public() for c in CAPABILITIES.values()]})
            lock = self.session_locks.setdefault(session, asyncio.Lock())
            async with lock:
                context = self.context(project)
                context["session"] = session
                context["applications"] = self.application_names()
                context["projects"] = [p["name"] for p in self.store.projects()]
                decision = await self.interpreter.decide(text, context)
        return self._decision(decision, text, project, session)

    def _local(self, decision, session):
        kind = decision.kind
        if kind == "greeting":
            return Response(decision.speech)
        if kind in ("agents", "capabilities"):
            agents = catalogue(self.interpreter.name if self.interpreter else "none")
            return Response(
                "Puedo buscar en la web, gestionar aplicaciones y ventanas y trabajar con archivos. "
                + ("Codex está configurado para programación. " if self.interpreter and
                   self.interpreter.name == "codex-chatgpt" else "")
                +
                "Los cambios y comandos requieren aprobación; la impresora sigue sin conectar.",
                data={"agents": agents, "capabilities": [c.public() for c in CAPABILITIES.values()]})
        if kind == "projects":
            projects = self.store.projects()
            return Response("Proyectos: " + ", ".join(p["name"] for p in projects) + "."
                            if projects else "No hay proyectos registrados.", data=projects)
        if kind in ("gaming_on", "gaming_off"):
            self.store.set_setting("gaming", kind == "gaming_on")
            self.notifications.clear()
            return Response("Modo gaming activado." if kind == "gaming_on" else "Modo normal activado.")
        tasks = self.store.tasks(session)
        current = [t for t in tasks if t["status"] not in TERMINAL]
        if not current:
            speech = "No hay tareas activas."
        else:
            running = sum(t["status"] == Status.RUNNING for t in current)
            queued = sum(t["status"] == Status.QUEUED for t in current)
            speech = f"{running} en ejecución, {queued} en cola y {len(current)-running-queued} pendientes o bloqueadas."
        return Response(speech, data=current)

    def _decision(self, decision, text, project, session):
        if decision.kind in ("answer", "clarify"):
            # No execution can be claimed by a model-only response.
            if decision.kind == "answer":
                import re
                if re.search(r"\b(?:he (?:abierto|modificado|enviado|iniciado|terminado|ejecutado)|"
                             r"estoy (?:trabajando|ejecutando)|i(?:'m| am) working|"
                             r"i (?:opened|changed|sent|started|completed)|task (?:started|completed))\b",
                             decision.speech, re.I):
                    return Response("No se ha ejecutado ninguna operación para esa petición.", "clarify")
            return Response(decision.speech, decision.kind, route="provider")
        if decision.kind == "capability":
            cap = CAPABILITIES.get(decision.capability)
            if not cap:
                raise ArgosError("La capacidad solicitada no está registrada.")
            cap.validate(decision.arguments)
            if cap.needs_project and not project:
                task = self.store.create_task(session, None, cap.agent, text, cap.name,
                                              decision.arguments, Status.WAITING_INPUT,
                                              "¿En qué proyecto registrado?")
                return Response(task["question"], "clarify", task["id"])
            self._check_queue()
            task = self.store.create_task(session, project["id"] if project else None,
                                          cap.agent, text, cap.name, decision.arguments)
            self.queue.put_nowait(task["id"])
            return Response("Petición aceptada.", "accepted", task["id"],
                            data={"status": "QUEUED", "agent": cap.agent})
        if decision.kind == "delegate" and decision.agent in AGENTS:
            if decision.agent in ("engineering", "design3d", "printing3d") and not project:
                task = self.store.create_task(session, None, decision.agent, text,
                                              status=Status.WAITING_INPUT,
                                              question="¿En qué proyecto registrado?")
                return Response(task["question"], "clarify", task["id"])
            if not self.interpreter:
                task = self.store.create_task(
                    session, project["id"] if project else None, decision.agent, text,
                    status=Status.BLOCKED,
                    question="El especialista está definido, pero no tiene un proveedor de IA conectado.")
                return Response(task["question"], "blocked", task["id"])
            self._check_queue()
            task = self.store.create_task(session, project["id"] if project else None,
                                          decision.agent, text)
            self.queue.put_nowait(task["id"])
            return Response("Petición aceptada por el especialista.", "accepted", task["id"])
        raise ArgosError("La decisión no puede ejecutarse.")

    async def _answer(self, task, text):
        if task["status"] != Status.WAITING_INPUT:
            raise ArgosError("La tarea no espera una respuesta.")
        if not task["project"] and task["agent"] in ("engineering", "design3d", "printing3d"):
            try:
                project = self.store.project(text)
            except ArgosError:
                return Response("Necesito el nombre exacto de un proyecto registrado.", "clarify", task["id"])
            task = self.store.update(task["id"], Status.WAITING_INPUT, project=project["id"])
        else:
            self.store.event(task["id"], "USER_ANSWER", {"answer": text})
        if not task["capability"] and not self.interpreter:
            self.store.update(task["id"], Status.BLOCKED,
                              question="Falta conectar el proveedor del especialista.")
            return Response("Falta conectar el proveedor del especialista.", "blocked", task["id"])
        self._enqueue(task)
        return Response("La misma tarea vuelve a la cola.", "accepted", task["id"])

    def _check_queue(self):
        if self.queue.full() or len(self.dispatches) + self.queue.qsize() >= 64:
            raise ArgosError("La cola está llena. Espera a que termine una tarea.")

    def _enqueue(self, task):
        self._check_queue()
        self.store.update(task["id"], Status.QUEUED)
        self.queue.put_nowait(task["id"])

    @staticmethod
    def describe(task):
        return f"{task['agent']}: {task['status']}. " + (task["question"] or
                (task["result"] or {}).get("speech", ""))

    async def _worker(self):
        while True:
            task_id = await self.queue.get()
            job = asyncio.create_task(self._dispatch_task(task_id))
            self.dispatches.add(job)
            job.add_done_callback(self.dispatches.discard)

    async def _dispatch_task(self, task_id):
        try:
            task = self.store.task(task_id)
            if task["status"] != Status.QUEUED:
                return
            lock = self.resource_locks.setdefault(task["project"] or task["agent"], asyncio.Lock())
            # Wait for project ownership BEFORE consuming an execution slot.
            # Several queued tasks for A must not starve an independent task B.
            async with lock:
                async with self.execution_slots:
                    if self.store.task(task_id)["status"] != Status.QUEUED:
                        return
                    job = asyncio.create_task(self._run(task_id))
                    self.active[task_id] = job
                    try:
                        await job
                    except asyncio.CancelledError:
                        if self.closing:
                            raise
                    finally:
                        self.active.pop(task_id, None)
        finally:
            self.queue.task_done()

    async def _run(self, task_id):
        task = self.store.update(task_id, Status.RUNNING)
        started = time.perf_counter()
        try:
            project = self.store.project(task["project"])
            if project:
                project["commands"] = self.store.setting("commands:" + project["id"], {})
            if not task["capability"]:
                events = self.store.events(task_id)
                context = self.context(project, task["agent"])
                context["task"] = {"id": task_id, "objective": task["objective"],
                                   "answers": [e["data"]["answer"] for e in reversed(events)
                                               if e["kind"] == "USER_ANSWER"][-8:]}
                if project:
                    context["commands"] = [
                        {"command": name, "expected_sha256":
                         hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()}
                        for name, spec in project["commands"].items()]
                if hasattr(self.interpreter, "work"):
                    history = [e["data"] for e in reversed(events) if e["kind"] == "CAPABILITY_RESULT"]
                    approved = next((e["data"] for e in events if e["kind"] == "APPROVED"), None)
                    if approved and self.policy.is_approved(self.operation(
                            task_id, approved["capability"], approved["arguments"], task["project"])):
                        result = await self.execute_capability(
                            task, project, approved["capability"], approved["arguments"])
                        history.append({"capability": approved["capability"], "result": result})
                    context["previous_operations"] = history[-12:]
                    async def execute(name, args):
                        if name not in AGENTS[task["agent"]].capabilities:
                            raise ArgosError("La capacidad está fuera del alcance de este especialista.")
                        result = await self.execute_capability(task, project, name, args)
                        history.append({"capability": name, "result": result})
                        return result
                    def save_thread(thread):
                        self.store.update(task_id, Status.RUNNING, thread_id=thread)
                    def progress(text):
                        try:
                            public_text(text, 4000)
                            self.store.event(task_id, "PROGRESS", {"summary": text})
                        except ArgosError:
                            pass
                    result = await self.interpreter.work(task, context, execute, save_thread, progress)
                    if result.get("kind") == "question":
                        self.store.update(task_id, Status.WAITING_INPUT, question=result["speech"])
                    elif history:
                        last_write = max((i for i, h in enumerate(history)
                                          if h["capability"] == "files.write"), default=-1)
                        checks = [h for i, h in enumerate(history) if i > last_write
                                  and h["capability"] == "commands.run"]
                        failed = bool(checks and checks[-1]["result"].get("verification") == "command_failed")
                        verified = bool(checks and checks[-1]["result"].get("verification") == "command_passed")
                        writes = any(h["capability"] == "files.write" for h in history)
                        outcome = {"speech": result["speech"], "detail": result["detail"],
                                   "verification": "command_failed" if failed else
                                       "command_passed" if verified else "changes_not_tested" if writes else "inspection_only",
                                   "operations": len(history)}
                        self.store.update(task_id, Status.FAILED if failed else Status.COMPLETED, result=outcome)
                    else:
                        self.store.update(task_id, Status.BLOCKED,
                                          result={"speech": result.get("speech", ""), "verification": "proposal_only"},
                                          question="Codex respondió sin ejecutar operaciones.")
                    self._notify(task_id, result.get("speech", ""))
                    return
                decision = await self.interpreter.decide(task["objective"], context, task["agent"])
                if decision.kind == "clarify":
                    self.store.update(task_id, Status.WAITING_INPUT, question=decision.speech)
                    self._notify(task_id, decision.speech)
                    return
                if decision.kind != "capability":
                    # Specialist model prose is an advisory result, never implementation.
                    self.store.update(task_id, Status.BLOCKED,
                                      result={"speech": decision.speech, "verification": "proposal_only"},
                                      question="No se ha ejecutado ninguna capacidad.")
                    self._notify(task_id, "El especialista ha devuelto una propuesta; no ha ejecutado cambios.")
                    return
                cap = CAPABILITIES.get(decision.capability)
                if not cap or cap.name not in AGENTS[task["agent"]].capabilities:
                    raise ArgosError("La capacidad propuesta está fuera del especialista.")
                task = self.store.update(task_id, Status.RUNNING, capability=cap.name,
                                          arguments=decision.arguments)
            result = await self.execute_capability(task, project, task["capability"], task["arguments"])
            result["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
            self.store.update(task_id, Status.FAILED if result.get("verification") == "command_failed"
                              else Status.COMPLETED, result=result)
            self._notify(task_id, result["speech"])
        except ApprovalNeeded as error:
            self.store.update(task_id, Status.WAITING_APPROVAL,
                              result={"pending_operation": error.pending},
                              question=f"Necesito aprobación para {error.pending['capability']}.")
            self._notify(task_id, f"La operación {error.pending['capability']} está preparada y necesita tu aprobación.")
        except asyncio.CancelledError:
            if self.store.task(task_id)["status"] == Status.RUNNING:
                self.store.update(task_id, Status.INTERRUPTED if self.closing else Status.CANCELLED)
            raise
        except Exception as error:
            message = str(error) if isinstance(error, ArgosError) else (
                "La operación no pudo completarse. Comprueba el archivo, formato o herramienta requerida.")
            self.store.update(task_id, Status.FAILED, question=message)
            self._notify(task_id, message)

    def _notify(self, task_id, speech):
        if not self.store.setting("gaming", False):
            self.notifications.append({"task_id": task_id, "speech": speech})
            if self.speech and speech:
                self.speech.enqueue(speech)

    @staticmethod
    def application_names():
        from .linux_tools import discover_apps
        return [{"id": a["id"], "name": a["name"]} for a in discover_apps().values()][:100]

    @staticmethod
    def operation(task_id, name, args, project):
        return Operation(name, {**args, "_task_id": task_id}, project, CAPABILITIES[name].effect)

    async def execute_capability(self, task, project, name, args):
        cap = CAPABILITIES.get(name)
        if not cap:
            raise ArgosError("La capacidad no existe.")
        cap.validate(args)
        if cap.needs_project and not project:
            raise ArgosError("Falta el proyecto para ejecutar la capacidad.")
        operation = self.operation(task["id"], name, args, task["project"])
        if not self.policy.is_approved(operation):
            pending = {"capability": name, "arguments": args, "effect": cap.effect,
                       "fingerprint": operation.fingerprint}
            if name == "commands.run":
                spec = project.get("commands", {}).get(args["command"])
                if not spec:
                    raise ArgosError("El comando no está registrado en este proyecto.")
                pending["review"] = {"argv": spec["argv"], "cwd": project["root"],
                                     "scope": "Ejecuta código local con los permisos de tu usuario."}
            raise ApprovalNeeded(pending)
        self.policy.authorize(operation)
        self.store.event(task["id"], "CAPABILITY_STARTED", {"capability": name})
        result = await asyncio.wait_for(cap.execute(project, args), 150)
        safe_data(result)
        self.store.event(task["id"], "CAPABILITY_RESULT", {"capability": name, "result": result})
        return result
