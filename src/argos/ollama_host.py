"""Start an already-installed local Ollama engine when the user opens ARGOS."""
import asyncio
import json
import os
from pathlib import Path
import shutil
import subprocess
import urllib.request

from .models import ArgosError


def available():
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open("http://127.0.0.1:11434/api/version", timeout=1) as reply:
            return bool(json.loads(reply.read(4096)).get("version"))
    except (OSError, ValueError):
        return False


async def ensure(directory):
    if await asyncio.to_thread(available):
        return
    bundled = Path.home() / ".local/share/argos/ollama-runtime/bin/ollama"
    binary = shutil.which("ollama") or (str(bundled) if bundled.is_file() else None)
    if not binary:
        raise ArgosError("Falta instalar Ollama. No se descarga ni se sustituye por Codex al abrir ARGOS.")
    env = {**os.environ, "OLLAMA_HOST": "127.0.0.1:11434", "OLLAMA_NO_CLOUD": "1", "OLLAMA_DEBUG": "0",
           "OLLAMA_NUM_PARALLEL": "1", "OLLAMA_MAX_LOADED_MODELS": "1"}
    if Path(binary).resolve() == bundled:
        env["OLLAMA_MODELS"] = str(bundled.parents[2] / "ollama-models")
    fd = os.open(directory / "ollama.log", os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "ab") as output:
        child = subprocess.Popen([binary, "serve"], stdin=subprocess.DEVNULL, stdout=output, stderr=output,
                                 env=env, start_new_session=True)
    for _ in range(30):
        if await asyncio.to_thread(available):
            return
        if child.poll() is not None:
            break
        await asyncio.sleep(.1)
    raise ArgosError("Ollama no arrancó. Revisa ollama.log; no se ha conectado Codex como sustituto.")
