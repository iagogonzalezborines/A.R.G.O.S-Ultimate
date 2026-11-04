"""Explicit provider selection per installation; no model downloads or inference."""
import json
import os
import tempfile

from .models import ArgosError


def read(directory):
    path = directory / "inference.json"
    if not path.exists():
        return {"ollama_model": None, "codex_escalation": False}
    try:
        settings = json.loads(path.read_text())
        validate(settings)
        return settings
    except (OSError, ValueError, TypeError):
        raise ArgosError("La configuración de proveedores no es válida.") from None


def validate(settings):
    base = {"ollama_model", "codex_escalation"}
    profiles = {"codex_model", "codex_effort", "codex_complex_model", "codex_complex_effort"}
    if not isinstance(settings, dict) or not base <= set(settings) or set(settings) - base - profiles - {"conversation_provider"}:
        raise ArgosError("La configuración de proveedores no es válida.")
    codex_mode = settings.get("conversation_provider") == "codex"
    model = settings["ollama_model"]
    if ((not codex_mode or model is not None) and
            (not isinstance(model, str) or not model.strip() or len(model) > 100 or "cloud" in model.casefold())):
        raise ArgosError("Selecciona un modelo Ollama local.")
    if (
            not isinstance(settings["codex_escalation"], bool)
            or settings.get("conversation_provider", "ollama") not in ("ollama", "nvidia", "codex")):
        raise ArgosError("Selecciona un modelo Ollama local y si permites escaladas a Codex.")
    if codex_mode:
        if not profiles <= set(settings) or not settings["codex_escalation"]:
            raise ArgosError("Codex requiere perfiles explícitos para conversación y tareas complejas.")
        for key in profiles:
            value = settings[key]
            if not isinstance(value, str) or not value or len(value) > 100 or any(c.isspace() for c in value):
                raise ArgosError("Perfil Codex inválido.")
        for key in ("codex_effort", "codex_complex_effort"):
            if settings[key] not in ("low", "medium", "high", "xhigh", "max"):
                raise ArgosError("Esfuerzo Codex no admitido.")
    elif profiles & set(settings):
        raise ArgosError("Los perfiles Codex requieren conversation_provider=codex.")


def write(directory, model, codex, conversation_provider="ollama", **profiles):
    settings = {"ollama_model": model, "codex_escalation": codex}
    if conversation_provider != "ollama":
        settings["conversation_provider"] = conversation_provider
    settings.update(profiles)
    validate(settings)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary = tempfile.mkstemp(prefix="inference-", dir=directory)
    try:
        with os.fdopen(descriptor, "w") as stream:
            json.dump(settings, stream)
            stream.write("\n")
        os.replace(temporary, directory / "inference.json")
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return settings
