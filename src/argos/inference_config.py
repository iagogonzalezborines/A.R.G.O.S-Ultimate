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
    if (not isinstance(settings, dict) or set(settings) != {"ollama_model", "codex_escalation"}
            or not isinstance(settings["ollama_model"], str) or not settings["ollama_model"].strip()
            or len(settings["ollama_model"]) > 100 or "cloud" in settings["ollama_model"].casefold()
            or not isinstance(settings["codex_escalation"], bool)):
        raise ArgosError("Selecciona un modelo Ollama local y si permites escaladas a Codex.")


def write(directory, model, codex):
    settings = {"ollama_model": model, "codex_escalation": codex}
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
