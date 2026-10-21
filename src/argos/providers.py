"""Optional structured interpreter. No provider is enabled or downloaded implicitly."""
import asyncio
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Protocol

from .agents import AGENTS, contract, local_contract
from .capabilities import CAPABILITIES
from .models import ArgosError, Decision, EscalationNeeded
from .security import safe_data


SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "kind": {"enum": ["answer", "clarify", "delegate", "capability", "panel", "reply", "develop", "task_status", "escalate"]},
        "speech": {"type": "string"}, "agent": {"type": "string"},
        "capability": {"type": "string"}, "arguments": {"type": "object"},
    },
    "required": ["kind", "speech", "agent", "capability", "arguments"],
}


class Interpreter(Protocol):
    name: str

    async def decide(self, text: str, context: dict, agent: str = "general") -> Decision: ...


def local_schema(context, agent="general"):
    """Constrain operation fields by decision kind, not just by prompt prose."""
    branches = []
    def add(kind, actor="", capability="", arguments=None):
        branches.append({"type": "object", "additionalProperties": False,
                         "properties": {"kind": {"const": kind}, "speech": {"type": "string", "maxLength": 4000},
                                        "agent": {"const": actor}, "capability": {"const": capability},
                                        "arguments": arguments or {"type": "object", "properties": {}, "additionalProperties": False}},
                         "required": SCHEMA["required"]})
    def argument(name, values=None):
        value = {"type": "string", **({"enum": values} if values is not None else {})}
        return {"type": "object", "properties": {name: value}, "required": [name], "additionalProperties": False}
    for kind in ("answer", "clarify"):
        if kind == "answer" and agent != "general" and not context.get("previous_operations"):
            continue  # Task completion requires tool evidence; a proposal is not execution.
        add(kind)
    for cap in context.get("capabilities", []):
        if cap["name"] not in CAPABILITIES or (agent != "general" and cap["name"] not in AGENTS[agent].capabilities):
            continue
        properties = {name: {"type": "string"} for name in cap["arguments"]}
        add("capability", cap["agent"], cap["name"],
            {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False})
    if agent == "general":
        for role in AGENTS:
            if role != "general":
                add("delegate", role)
        if any(c["name"] == "development.plan" for c in context.get("capabilities", [])):
            add("develop", arguments=argument("target", ["self", "project", "new"]))
        add("task_status", arguments=argument("task_id", ["all"] + [t["id"] for t in context.get("tasks", [])]))
        questions = [q["task_id"] for q in context.get("pending_questions", [])]
        if questions:
            add("reply", arguments=argument("task_id", questions))
        if context.get("panels"):
            add("panel", arguments=argument("view", context["panels"]))
    elif agent in ("engineering", "research") and context.get("escalation", {}).get("allowed"):
        add("escalate", arguments=argument("reason"))
    # Ollama may serialize schema properties alphabetically. Keep the decision
    # discriminator ahead of agent/tool fields: choosing an agent first biases
    # constrained decoding towards a tool even for ordinary conversation.
    names = {"agent": "target_agent", "capability": "tool", "arguments": "tool_arguments"}
    for branch in branches:
        branch["properties"] = {names.get(key, key): value for key, value in branch["properties"].items()}
        branch["required"] = [names.get(key, key) for key in branch["required"]]
    return {"type": "object", "oneOf": branches}


def validate_decision(data, agent="general"):
    if not isinstance(data, dict) or set(data) != set(SCHEMA["required"]):
        raise ArgosError("El proveedor devolvió una decisión inválida.")
    if data["kind"] not in SCHEMA["properties"]["kind"]["enum"]:
        raise ArgosError("El proveedor devolvió un tipo de decisión no admitido.")
    if any(not isinstance(data[k], str) for k in ("speech", "agent", "capability")):
        raise ArgosError("El proveedor devolvió campos inválidos.")
    safe_data(data)
    if len(data["speech"]) > 4000 or not isinstance(data["arguments"], dict):
        raise ArgosError("El proveedor excedió los límites de respuesta.")
    if data["agent"] and data["agent"] not in AGENTS:
        raise ArgosError("El proveedor solicitó un agente inexistente.")
    if data["kind"] == "escalate":
        if (agent not in ("engineering", "research") or data["agent"] or data["capability"]
                or set(data["arguments"]) != {"reason"}
                or not isinstance(data["arguments"]["reason"], str)
                or not 16 <= len(data["arguments"]["reason"].strip()) <= 600):
            raise ArgosError("Solo una tarea local Engineering/Research puede justificar una escalada.")
    elif data["kind"] == "develop":
        if (agent != "general" or data["agent"] or data["capability"]
                or set(data["arguments"]) != {"target"}
                or data["arguments"]["target"] not in ("self", "project", "new")):
            raise ArgosError("El desarrollo debe seleccionar self, project o new.")
    elif data["kind"] == "task_status":
        if (agent != "general" or data["agent"] or data["capability"]
                or set(data["arguments"]) != {"task_id"}
                or not isinstance(data["arguments"]["task_id"], str)
                or (data["arguments"]["task_id"] != "all" and len(data["arguments"]["task_id"]) != 32)):
            raise ArgosError("El estado debe seleccionar una tarea del contexto o all.")
    elif data["kind"] == "reply":
        if (agent != "general" or data["agent"] or data["capability"]
                or set(data["arguments"]) != {"task_id"}
                or not isinstance(data["arguments"]["task_id"], str)
                or len(data["arguments"]["task_id"]) != 32):
            raise ArgosError("La respuesta debe identificar una pregunta pendiente concreta.")
    elif data["kind"] == "panel":
        if (agent != "general" or data["agent"] or data["capability"]
                or set(data["arguments"]) != {"view"}
                or data["arguments"]["view"] not in ("agents", "tasks")):
            raise ArgosError("El proveedor solicitó un panel no admitido.")
    elif data["kind"] == "capability":
        cap = CAPABILITIES.get(data["capability"])
        if not cap or (agent != "general" and cap.name not in AGENTS[agent].capabilities):
            raise ArgosError("El proveedor solicitó una capacidad fuera de su alcance.")
        cap.validate(data["arguments"])
        data = {**data, "agent": cap.agent}
    elif data["capability"] or data["arguments"]:
        raise ArgosError("Una respuesta no puede ocultar una operación.")
    if data["kind"] == "delegate" and data["agent"] in ("", "general"):
        raise ArgosError("La delegación no identifica un especialista.")
    return Decision(**data, reason="structured_provider_decision")


class OllamaInterpreter:
    name = "ollama"

    def __init__(self, model, url="http://127.0.0.1:11434"):
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
            raise ArgosError("Esta base solo conecta Ollama en la máquina local.")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ArgosError("La dirección de Ollama no debe contener credenciales.")
        if not model or len(model) > 100 or "cloud" in model.casefold():
            raise ArgosError("Indica un modelo local ya instalado.")
        self.model, self.url = model, url.rstrip("/")
        self.slots = asyncio.Semaphore(1)
        self.connected = False
        self.metrics = {}
        self.local_verified = False
        self.last_public_decision = None

    async def decide(self, text, context, agent="general"):
        safe_data(context)
        self.last_public_decision = None
        # Put stable registry data before the changing turn so Ollama can reuse
        # the prompt prefix. This is the same context, not another routing call.
        ordered = {key: context[key] for key in ("capabilities", "agents", "identity", "inference", "scope") if key in context}
        if "capabilities" in ordered:
            ordered["capabilities"] = [{key: cap[key] for key in ("name", "agent", "arguments", "status") if key in cap}
                                       for cap in ordered["capabilities"]]
        if "agents" in ordered:
            ordered["agents"] = [{"id": item["id"], "role": item["role"]} for item in ordered["agents"]]
        ordered.update({key: value for key, value in context.items() if key not in ordered})
        if agent == "general" and "environment" in ordered:
            environment = ordered["environment"]
            ordered["environment"] = {key: environment[key] for key in ("status", "stale", "observed_at") if key in environment}
            ordered["environment"]["facts"] = {key: value for key, value in environment.get("facts", {}).items()
                                                 if key in ("system", "cpu", "memory", "graphics", "permissions", "voice_environment")}
            ordered["environment"]["limits"] = environment.get("limits", [])
            ordered["environment"]["detail"] = "Summary only; use system.inspect for tools, storage and device details."
        recent = ordered.pop("recent_conversation", [])
        messages = [
            {"role": "system", "content": local_contract(agent)},
            {"role": "user", "content": "Runtime context (data, not a user request):\n" +
             json.dumps(ordered, ensure_ascii=False, separators=(",", ":"))},
        ]
        messages.extend({"role": item["role"], "content": item["content"]}
                        for item in recent if item.get("role") in ("user", "assistant"))
        messages.append({"role": "user", "content": text})
        payload = {
            "model": self.model, "stream": False, "format": local_schema(context, agent), "think": False,
            "keep_alive": "10m", "options": {"num_ctx": 16384, "num_predict": 2048, "temperature": 0.3},
            "messages": messages,
        }

        def request():
            req = urllib.request.Request(self.url + "/api/chat",
                                         json.dumps(payload).encode(),
                                         {"Content-Type": "application/json"}, method="POST")
            # Never forward local prompts to a redirected host or an environment proxy.
            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, *args, **kwargs):
                    return None
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
            if not self.local_verified:
                probe = urllib.request.Request(self.url + "/api/show", json.dumps({"model": self.model}).encode(),
                                               {"Content-Type": "application/json"}, method="POST")
                with opener.open(probe, timeout=10) as reply:
                    info = json.loads(reply.read(2 * 1024 * 1024))
                if info.get("remote_host") or info.get("remote_model") or not info.get("details"):
                    raise ArgosError("La conversación requiere un modelo instalado localmente, no un modelo cloud.")
                self.local_verified = True
            with opener.open(req, timeout=180) as reply:
                body = reply.read(128001)
            if len(body) > 128000:
                raise ArgosError("La respuesta del proveedor excede el límite.")
            envelope = json.loads(body)
            self.metrics = {key: envelope.get(key) for key in (
                "model", "total_duration", "load_duration", "prompt_eval_count", "prompt_eval_duration", "eval_count", "eval_duration")}
            if envelope.get("done") is not True:
                raise ArgosError("El proveedor no completó la respuesta.")
            wire = json.loads(envelope["message"]["content"])
            if not isinstance(wire, dict) or set(wire) != {"kind", "speech", "target_agent", "tool", "tool_arguments"}:
                raise ArgosError("El proveedor devolvió una decisión local inválida.")
            decision = {"kind": wire["kind"], "speech": wire["speech"], "agent": wire["target_agent"],
                        "capability": wire["tool"], "arguments": wire["tool_arguments"]}
            safe_data(decision)
            self.last_public_decision = decision
            return validate_decision(decision, agent)

        async with self.slots:
            try:
                result = await asyncio.to_thread(request)
                self.connected = True
                return result
            except ArgosError:
                raise
            except (OSError, ValueError, KeyError, TypeError):
                self.connected = False
                raise ArgosError("El proveedor local no respondió correctamente. Comprueba Ollama y el modelo.") from None

    async def work(self, task, context, execute, save_thread, progress):
        """Bounded local tool loop; Core still authorizes every effect.

        No remote fallback, and no extra routing/acknowledgement inference.
        Approval/plan suspension propagates immediately to the Core.
        """
        history = list(context.get("previous_operations", []))
        for _ in range(12):
            context["previous_operations"] = history[-12:]
            decision = await self.decide(task["objective"], context, task["agent"])
            if decision.kind == "escalate":
                raise EscalationNeeded(decision.arguments["reason"])
            if decision.kind in ("answer", "clarify"):
                return {"kind": "question" if decision.kind == "clarify" else "result",
                        "speech": decision.speech, "detail": decision.speech}
            if decision.kind != "capability":
                raise ArgosError("La tarea local debe usar una capacidad, responder o justificar una escalada.")
            if any(h.get("capability") == decision.capability and h.get("arguments") == decision.arguments
                   for h in history):
                raise ArgosError("La tarea local repitió una operación sin avanzar; requiere revisión.")
            result = await execute(decision.capability, decision.arguments)
            history.append({"capability": decision.capability, "arguments": decision.arguments, "result": result})
        raise ArgosError("La tarea local alcanzó su límite de pasos; no se ha recurrido a Codex automáticamente.")
