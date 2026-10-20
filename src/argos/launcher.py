"""User-requested session startup. No boot service and no shared process termination."""
import asyncio
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .models import ArgosError
from .transport import call


async def start(directory, project=None):
    executable = Path(__file__).resolve().parents[2] / "argos"
    if not executable.is_file():
        raise ArgosError("El lanzador requiere ejecutar ARGOS desde este checkout.")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    command = [sys.executable, str(executable), "--state-dir", str(directory)]
    try:
        state = await call(directory, {"method": "voice.state"})
    except ArgosError:
        log = directory / "core.log"
        fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "ab") as stream:
            subprocess.Popen([*command, "serve", "--codex", "--voice"],
                             stdin=subprocess.DEVNULL, stdout=stream, stderr=stream, start_new_session=True)
        for _ in range(50):
            await asyncio.sleep(0.1)
            try:
                state = await call(directory, {"method": "voice.state"})
                break
            except ArgosError:
                continue
        else:
            raise ArgosError("Core no arrancó. Revisa core.log en la carpeta de estado.")
    if state["data"].get("stt") == "not_connected":
        raise ArgosError("El Core activo no tiene voz. Ciérralo antes de iniciar la configuración de voz.")
    if project:
        projects = (await call(directory, {"method": "projects.list"}))["data"]
        if project.casefold() not in [p["name"].casefold() for p in projects]:
            raise ArgosError("Ese proyecto no está registrado.")
    terminal = shutil.which("kitty")
    if not terminal:
        raise ArgosError("Falta kitty. Puedes abrir «argos console» en tu terminal.")
    console = [*command, "console", *(["--project", project] if project else [])]
    subprocess.Popen([terminal, "--class", "argos", "--title", "ARGOS", *console],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)
