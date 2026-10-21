import asyncio
import hashlib
import math
import os
import platform
import re
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .models import ArgosError
from .security import safe_data, scoped_file


@dataclass(frozen=True)
class Capability:
    name: str
    agent: str
    description: str
    arguments: tuple[str, ...]
    needs_project: bool
    execute: Callable
    effect: str = "read"

    def validate(self, args):
        if not isinstance(args, dict) or set(args) != set(self.arguments):
            raise ArgosError(f"Argumentos incorrectos para {self.name}.")
        if any(not isinstance(v, str) or len(v) > (64000 if k == "content" else 2000)
               or (not v and k not in ("content", "expected_sha256")) for k, v in args.items()):
            raise ArgosError("Los argumentos deben ser textos válidos.")
        safe_data(args)

    def public(self, availability=None):
        return dict(name=self.name, agent=self.agent, description=self.description,
                    arguments=list(self.arguments), needs_project=self.needs_project,
                    effect=self.effect, implemented=True,
                    **(availability or {"available": None, "status": "not_checked",
                                       "reason": "Entorno no comprobado.", "checked_at": None}))


async def system_info(project, args):
    return {"speech": f"Linux {platform.release()}. {os.cpu_count()} CPU lógicas disponibles.",
            "evidence": {"os": platform.system(), "release": platform.release(),
                         "architecture": platform.machine(), "cpu_count": os.cpu_count()},
            "verification": "host_observed"}


async def git_read(root, *args):
    env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
           "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0"}
    proc = await asyncio.create_subprocess_exec(
        "git", "-c", "core.fsmonitor=false", "-C", root, *args, env=env,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), 5)
    except (TimeoutError, asyncio.CancelledError):
        if proc.returncode is None:
            proc.kill()
        await proc.wait()
        raise
    if len(out) > 64000:
        raise ArgosError("El estado del repositorio excede el límite de esta inspección.")
    return out.decode("utf-8", errors="replace").strip() if proc.returncode == 0 else None


async def repo_inspect(project, args):
    root = project["root"]
    names = sorted(p.name for p in Path(root).iterdir()
                   if not p.name.startswith(".") and p.name not in ("node_modules", "vendor"))[:60]
    top = await git_read(root, "rev-parse", "--show-toplevel")
    is_repo = top is not None and Path(top).resolve() == Path(root).resolve()
    head = await git_read(root, "rev-parse", "--verify", "HEAD") if is_repo else None
    status = await git_read(root, "status", "--porcelain=v1", "--untracked-files=no") if is_repo else None
    return {"speech": f"He inspeccionado {project['name']}. "
                      + ("El repositorio tiene cambios." if status else
                         "Sin cambios en archivos seguidos." if is_repo else "No tiene un repositorio Git propio."),
            "evidence": {"project": project["name"], "entries": names, "git": is_repo,
                         "head": head, "tracked_changes": status},
            "verification": "metadata_observed",
            "limits": "No se han leído fuentes, ejecutado pruebas ni modificado archivos."}


def stl_data(data):
    low, high, count = [math.inf] * 3, [-math.inf] * 3, 0

    def add(point):
        nonlocal count
        if not all(math.isfinite(v) for v in point):
            raise ArgosError("El STL contiene coordenadas no finitas.")
        for i, value in enumerate(point):
            low[i] = min(low[i], value)
            high[i] = max(high[i], value)
        count += 1

    if len(data) >= 84 and len(data) == 84 + struct.unpack_from("<I", data, 80)[0] * 50:
        triangles = struct.unpack_from("<I", data, 80)[0]
        for offset in range(84, len(data), 50):
            values = struct.unpack_from("<12fH", data, offset)
            for point in (values[3:6], values[6:9], values[9:12]):
                add(point)
        encoding = "binary"
    else:
        text = data.decode("ascii", errors="strict")
        for line in text.splitlines():
            parts = line.strip().split()
            if parts and parts[0].lower() == "vertex":
                if len(parts) != 4:
                    raise ArgosError("El STL contiene un vértice inválido.")
                add(tuple(float(x) for x in parts[1:]))
        if not text.lstrip().lower().startswith("solid") or count % 3:
            raise ArgosError("El archivo no tiene estructura STL reconocible.")
        triangles = count // 3
        encoding = "ascii"
    if not count:
        raise ArgosError("El STL está vacío.")
    return dict(triangles=triangles, encoding=encoding, minimum=low, maximum=high,
                dimensions=[high[i] - low[i] for i in range(3)], units="unspecified")


def read_artifact(project, filename, suffix):
    path = scoped_file(project["root"], filename, suffix)
    # Open every component relative to an already-open directory descriptor.
    # This closes parent-symlink substitution races on Linux.
    flags = os.O_RDONLY | os.O_NOFOLLOW
    directory = os.open(project["root"], flags | os.O_DIRECTORY)
    try:
        parts = path.relative_to(Path(project["root"])).parts
        for part in parts[:-1]:
            next_directory = os.open(part, flags | os.O_DIRECTORY, dir_fd=directory)
            os.close(directory)
            directory = next_directory
        fd = os.open(parts[-1], flags, dir_fd=directory)
    finally:
        os.close(directory)
    with os.fdopen(fd, "rb") as f:
        data = f.read(32 * 1024 * 1024 + 1)
    if len(data) > 32 * 1024 * 1024:
        raise ArgosError("El artefacto excede 32 MiB.")
    return data, hashlib.sha256(data).hexdigest()


async def stl_inspect(project, args):
    def inspect():
        data, digest = read_artifact(project, args["file"], ".stl")
        return stl_data(data), digest
    result, digest = await asyncio.to_thread(inspect)
    return {"speech": f"El STL contiene {result['triangles']} triángulos. Sus unidades no están declaradas.",
            "evidence": {**result, "file": args["file"], "sha256": digest},
            "verification": "geometry_measured",
            "limits": "No comprueba estanqueidad, resistencia ni posibilidad de impresión."}


async def gcode_inspect(project, args):
    def inspect():
        data, digest = read_artifact(project, args["file"], ".gcode")
        if b"\x00" in data:
            raise ArgosError("Se esperaba G-code de texto.")
        text = data.decode("utf-8", errors="strict")
        movements, tool_temperatures, bed_temperatures = 0, [], []
        for line in text.splitlines():
            command = re.sub(r"\([^)]*\)", "", line.split(";", 1)[0]).upper().strip()
            command = re.sub(r"^N\d+\s*", "", command)
            if re.match(r"G0?[01](?:\s|[XYZEF]|$)", command):
                movements += 1
            m = re.match(r"M(104|109|140|190)\s*(.*)", command)
            if m:
                value = re.search(r"S\s*(-?\d+(?:\.\d+)?)", m[2])
                if value:
                    target = tool_temperatures if m[1] in ("104", "109") else bed_temperatures
                    target.append(float(value[1]))
        return dict(file=args["file"], sha256=digest, lines=len(text.splitlines()),
                    linear_moves=movements, declared_tool_temperatures=sorted(set(tool_temperatures)),
                    declared_bed_temperatures=sorted(set(bed_temperatures)))
    result = await asyncio.to_thread(inspect)
    return {"speech": f"He revisado el G-code: {result['linear_moves']} movimientos lineales. No se ha enviado a ninguna impresora.",
            "evidence": result, "verification": "metadata_parsed",
            "limits": "Inspección parcial; no certifica seguridad, compatibilidad ni tiempo de impresión."}


CAPABILITIES = {
    c.name: c for c in (
        Capability("system.info", "computer", "Consultar sistema y CPU", (), False, system_info),
        Capability("repo.inspect", "engineering", "Inspeccionar estado Git y entradas del proyecto", (), True, repo_inspect),
        Capability("stl.inspect", "design3d", "Medir triángulos y límites de un STL", ("file",), True, stl_inspect),
        Capability("gcode.inspect", "printing3d", "Revisar metadatos G-code sin imprimir", ("file",), True, gcode_inspect),
    )
}

from .linux_tools import capabilities as linux_capabilities
CAPABILITIES.update({c.name: c for c in linux_capabilities(Capability)})

from .filesystem import capabilities as filesystem_capabilities
from .web_reader import capabilities as web_capabilities
CAPABILITIES.update({c.name: c for c in filesystem_capabilities(Capability) + web_capabilities(Capability)})

from .host import inspect_system
CAPABILITIES["system.inspect"] = Capability(
    "system.inspect", "computer", "Inventario observado del equipo, herramientas, dispositivos y límites", (), False, inspect_system)
