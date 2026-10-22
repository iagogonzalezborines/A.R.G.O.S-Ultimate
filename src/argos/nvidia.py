"""Explicit NVIDIA conversation only. Core retains all operations and approvals."""
import asyncio
import json
import os
import stat
import urllib.error
import urllib.request

from .agents import local_contract
from .models import ArgosError
from .providers import decision_messages, local_schema, validate_decision
from .security import safe_data

MODEL = "nvidia/nemotron-3.5-super-vl-120b-a12b"
ENDPOINT = "https://integrate.api.nvidia.com/v1/chat/completions"


def read_private_key(path):
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "r", encoding="ascii") as stream:
            metadata = os.fstat(stream.fileno())
            if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid()
                    or metadata.st_mode & 0o077):
                raise ArgosError("La clave NVIDIA requiere archivo privado de tu usuario con permisos 0600.")
            key = stream.read(8194).strip()
        if not key or len(key) > 8192 or any(not 33 <= ord(c) <= 126 for c in key):
            raise ArgosError("El archivo de clave NVIDIA no contiene una credencial válida.")
        return key
    except (OSError, UnicodeError):
        raise ArgosError("No se pudo leer credentials/nvidia.key en la carpeta de estado de ARGOS.") from None


def matches_branch(wire, schema):
    # local_schema uses only constants, string arguments and finite enums here.
    for branch in schema["oneOf"]:
        props = branch["properties"]
        if any(wire.get(k) != props[k]["const"] for k in ("kind", "target_agent", "tool")):
            continue
        args = wire.get("tool_arguments")
        expected = props["tool_arguments"].get("properties", {})
        if not isinstance(args, dict) or set(args) != set(expected):
            continue
        if all(isinstance(value, str) and ("enum" not in expected[k] or value in expected[k]["enum"])
               for k, value in args.items()):
            return True
    return False



class NvidiaConversation:
    name = "nvidia"
    model = MODEL

    def __init__(self, key_file):
        self._key = read_private_key(key_file)
        self.connected = False
        self.metrics = {}
        self._slot = asyncio.Semaphore(1)

    def _opener(self):
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        return urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    async def decide(self, text, context, agent="general"):
        if agent != "general":
            raise ArgosError("Nemotron solo está configurado para conversación; las tareas conservan su proveedor.")
        safe_data(context)
        messages = decision_messages(text, context)
        messages[0]["content"] = local_contract().replace(
            "interaction contract — local", "interaction contract — NVIDIA conversation").replace(
            "Conversation and routine work always stay local.",
            "Conversation uses NVIDIA Nemotron. Routine tasks stay local; Core owns operations and approvals.")
        schema = local_schema(context)
        payload = {"model": MODEL, "messages": messages, "stream": False,
                   "temperature": 1.0, "top_p": 0.95, "max_tokens": 4096, "reasoning_effort": "none",
                   "response_format": {"type": "json_schema", "json_schema": {
                       "name": "argos_decision", "strict": True, "schema": schema}}}

        def request():
            req = urllib.request.Request(ENDPOINT, json.dumps(payload).encode(),
                {"Content-Type": "application/json", "Accept": "application/json",
                 "Authorization": "Bearer " + self._key}, method="POST")
            with self._opener().open(req, timeout=20) as reply:
                if reply.status != 200:
                    raise ArgosError("NVIDIA no devolvió una respuesta completa. Puedes volver a intentarlo.")
                raw = reply.read(128001)
            if len(raw) > 128000:
                raise ArgosError("NVIDIA excedió el tamaño máximo de respuesta.")
            envelope = json.loads(raw)
            choices = envelope.get("choices", [])
            if len(choices) != 1 or choices[0].get("finish_reason") != "stop":
                raise ArgosError("NVIDIA no terminó la respuesta; no se reproducirá texto cortado.")
            message = choices[0]["message"]
            if message.get("tool_calls") or message.get("function_call"):
                raise ArgosError("NVIDIA devolvió una operación fuera del contrato de ARGOS.")
            # Never inspect, log, speak or persist reasoning_content.
            wire = json.loads(message["content"])
            if (not isinstance(wire, dict)
                    or set(wire) != {"kind", "speech", "target_agent", "tool", "tool_arguments"}
                    or not matches_branch(wire, schema)):
                raise ArgosError("NVIDIA devolvió una decisión inválida; no se ha ejecutado ninguna acción.")
            decision = validate_decision({"kind": wire["kind"], "speech": wire["speech"],
                "agent": wire["target_agent"], "capability": wire["tool"], "arguments": wire["tool_arguments"]})
            if decision.kind in ("answer", "clarify") and not decision.speech.strip():
                raise ArgosError("NVIDIA devolvió una respuesta vacía.")
            usage = envelope.get("usage", {})
            metrics = {key: usage[key] for key in ("prompt_tokens", "completion_tokens", "total_tokens")
                       if isinstance(usage.get(key), int)}
            return decision, metrics

        async with self._slot:
            self.metrics = {}
            try:
                decision, self.metrics = await asyncio.to_thread(request)
            except Exception as error:
                self.connected = False
                if isinstance(error, urllib.error.HTTPError):
                    error.close()
                    if error.code == 429:
                        raise ArgosError("NVIDIA ha alcanzado su límite de uso. Inténtalo más tarde.") from None
                    if error.code in (401, 403):
                        raise ArgosError("NVIDIA no acepta la credencial configurada.") from None
                    raise ArgosError("NVIDIA no está respondiendo correctamente. Puedes volver a intentarlo.") from None
                if isinstance(error, ArgosError):
                    raise
                raise ArgosError("No he recibido una respuesta válida de NVIDIA a tiempo. Puedes volver a intentarlo.") from None
            self.connected = True
            return decision
