"""Optional structured interpreter. No provider is enabled or downloaded implicitly."""
import asyncio
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Protocol

from .agents import AGENTS, contract
from .capabilities import CAPABILITIES
from .models import ArgosError, Decision
from .security import safe_data


SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "kind": {"enum": ["answer", "clarify", "delegate", "capability"]},
        "speech": {"type": "string"}, "agent": {"type": "string"},
        "capability": {"type": "string"}, "arguments": {"type": "object"},
    },
    "required": ["kind", "speech", "agent", "capability", "arguments"],
}


class Interpreter(Protocol):
    name: str

    async def decide(self, text: str, context: dict, agent: str = "general") -> Decision: ...


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
    if data["kind"] == "capability":
        cap = CAPABILITIES.get(data["capability"])
        if not cap or (agent != "general" and cap.agent != agent):
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
        if not model or len(model) > 100:
            raise ArgosError("Indica un modelo local ya instalado.")
        self.model, self.url = model, url.rstrip("/")
        self.slots = asyncio.Semaphore(1)

    async def decide(self, text, context, agent="general"):
        safe_data(context)
        payload = {
            "model": self.model, "stream": False, "format": SCHEMA,
            "keep_alive": "2m",
            "messages": [
                {"role": "system", "content": contract(agent)},
                {"role": "user", "content": json.dumps({"request": text, "context": context}, ensure_ascii=False)},
            ],
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
            with opener.open(req, timeout=30) as reply:
                body = reply.read(128001)
            if len(body) > 128000:
                raise ArgosError("La respuesta del proveedor excede el límite.")
            envelope = json.loads(body)
            if envelope.get("done") is not True:
                raise ArgosError("El proveedor no completó la respuesta.")
            return validate_decision(json.loads(envelope["message"]["content"]), agent)

        async with self.slots:
            try:
                return await asyncio.to_thread(request)
            except ArgosError:
                raise
            except (OSError, ValueError, KeyError, TypeError):
                raise ArgosError("El proveedor local no respondió correctamente. Comprueba Ollama y el modelo.") from None
