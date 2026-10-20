import hashlib
import json
import re
from pathlib import Path

from .models import ArgosError


SECRET = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----|"
    r"\b(?:sk-|ghp_|github_pat_|AIza)[A-Za-z0-9_-]{16,}|"
    r"\b(?:api[_ -]?key|password|passwd|token|secret|contraseña)\s*[:=]\s*\S+",
    re.I,
)


def public_text(text: str, limit: int = 16000) -> str:
    if not isinstance(text, str) or len(text) > limit:
        raise ArgosError("El texto falta o excede el límite permitido.")
    if SECRET.search(text):
        raise ArgosError("No envíes credenciales por conversación. Esta base no necesita ninguna.")
    if any(ord(c) < 32 and c not in "\n\t\r" for c in text):
        raise ArgosError("El texto contiene caracteres de control.")
    return text


def safe_data(value):
    # Reject obvious credentials before any database write or provider handoff.
    public_text(json.dumps(value, ensure_ascii=False), 200000)
    return value


def fingerprint(operation: str, arguments: dict, project: str | None) -> str:
    body = json.dumps([operation, arguments, project], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode()).hexdigest()


def scoped_file(root: str, relative: str, suffix: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ArgosError("Selecciona un archivo relativo al proyecto.")
    if any(part.startswith(".") for part in path.parts):
        raise ArgosError("Los archivos ocultos no se exponen al agente.")
    base = Path(root).resolve(strict=True)
    current = base
    for part in path.parts:
        current = current / part
        if current.is_symlink():
            raise ArgosError("No se permiten enlaces simbólicos para los artefactos.")
    target = current.resolve(strict=True)
    if not target.is_relative_to(base) or not target.is_file():
        raise ArgosError("El archivo no pertenece al proyecto.")
    if target.suffix.lower() != suffix or target.stat().st_size > 32 * 1024 * 1024:
        raise ArgosError("Formato no admitido o archivo mayor de 32 MiB.")
    return target
