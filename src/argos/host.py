"""Bounded Linux observations and capability prerequisites. Never opens audio."""
import asyncio
import copy
import os
import platform
import re
import shutil
import time
from pathlib import Path

from .models import ArgosError
from .security import safe_data


TOOLS = ("git", "python", "python3", "uv", "node", "npm", "cargo", "cmake",
         "docker", "code", "codex", "kitty", "hyprctl", "gio", "xdg-open",
         "pw-cli", "pw-dump", "pw-record", "pw-play", "pactl", "bwrap")


def observation(value, source, status="observed", reason=None):
    result = {"status": status, "value": value, "source": source, "observed_at": time.time()}
    if reason:
        result["reason"] = reason
    try:
        safe_data(result)
    except ArgosError:
        return {"status": "unavailable", "value": None, "source": source,
                "observed_at": time.time(), "reason": "Contenido omitido por el filtro de datos públicos."}
    return result


def read_text(path, limit=65536):
    with Path(path).open(encoding="utf-8") as file:
        return file.read(limit)


def collect_local():
    """Allowlisted metadata only; no recursive home scan, argv, env dump or IDs."""
    result = {}
    def collect(name, source, read):
        try:
            result[name] = observation(read(), source)
        except PermissionError:
            result[name] = observation(None, source, "permission_denied", "Permiso de lectura denegado.")
        except (OSError, ValueError, KeyError):
            result[name] = observation(None, source, "unavailable", "No se pudo obtener esta observación.")

    def system():
        info = platform.freedesktop_os_release()
        return {"os": platform.system(), "kernel": platform.release(), "architecture": platform.machine(),
                "distribution": info.get("PRETTY_NAME", "")[:160], "python": platform.python_version()}

    def cpu():
        text = read_text("/proc/cpuinfo")
        model = re.search(r"^(?:model name|Hardware)\s*:\s*(.+)$", text, re.M)
        return {"logical_cpus": os.cpu_count(), "model": model[1][:160] if model else None}

    def memory():
        fields = dict(re.findall(r"^(MemTotal|MemAvailable|SwapTotal):\s*(\d+) kB$",
                                 read_text("/proc/meminfo"), re.M))
        return {key: int(value) * 1024 for key, value in fields.items()}

    def graphics():
        devices = []
        for card in sorted(Path("/sys/class/drm").glob("card[0-9]*"))[:32]:
            if not re.fullmatch(r"card\d+", card.name):
                continue
            device = card / "device"
            try:
                devices.append({"card": card.name, "vendor_id": read_text(device / "vendor", 32).strip(),
                                "device_id": read_text(device / "device", 32).strip(),
                                "driver": (device / "driver").resolve(strict=True).name[:80]})
            except FileNotFoundError:
                continue
        return devices

    def storage():
        disks = []
        for path in dict.fromkeys(("/", str(Path.home()))):
            usage = shutil.disk_usage(path)
            disks.append({"path": path, "total_bytes": usage.total, "free_bytes": usage.free})
        return disks

    collect("system", "platform + /etc/os-release", system)
    collect("cpu", "/proc/cpuinfo + os.cpu_count", cpu)
    collect("memory", "/proc/meminfo", memory)
    collect("graphics", "/sys/class/drm (PCI identifiers; no serial numbers)", graphics)
    collect("storage", "statvfs(/, home); not an inventory of every mount", storage)
    collect("session", "allowlisted desktop environment indicators", lambda: {
        "type": os.environ.get("XDG_SESSION_TYPE", "unknown")[:32],
        "desktop": os.environ.get("XDG_CURRENT_DESKTOP", "unknown")[:80],
        "display_present": bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")),
        "hyprland_indicated": bool(os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"))})
    collect("tools", "executable lookup in PATH; no execution or version inference",
            lambda: {tool: bool(shutil.which(tool)) for tool in TOOLS})
    collect("permissions", "effective uid + os.access(home); path-specific checks occur at use", lambda: {
        "effective_uid": os.geteuid(), "root": os.geteuid() == 0, "home": str(Path.home()),
        "home_readable": os.access(Path.home(), os.R_OK), "home_writable": os.access(Path.home(), os.W_OK),
        "commands_sandboxed": False, "automatic_elevation": False})
    collect("voice_environment", "expected local voice Python executable", lambda: {
        "installed": (Path.home() / ".local/share/argos/voice-env/bin/python").is_file(),
        "models": "not_checked", "microphone_tested": False, "echo_cancellation_tested": False})
    result["network"] = observation(None, "no external requests", "not_checked",
                                    "No se ha comprobado conectividad, DNS ni acceso a sitios concretos.")
    return result


class LinuxEnvironment:
    """Injected into Core; snapshots expire and are never written to settings."""
    def __init__(self, ttl=30):
        self.ttl = ttl
        self.data = None
        self.updated = None
        self.lock = asyncio.Lock()

    async def refresh(self, force=False):
        requested = time.monotonic()
        async with self.lock:
            if self.updated is not None and (self.updated >= requested or
                    (not force and time.monotonic() - self.updated < self.ttl)):
                return self.snapshot()
            facts = await asyncio.to_thread(collect_local)
            tools = facts["tools"]["value"] or {}
            session = facts["session"]["value"] or {}
            async def probe(name, argv, extract):
                source = " ".join(argv)
                if not tools.get(argv[0]):
                    return name, observation(None, source, "unavailable", "Falta " + argv[0] + ".")
                try:
                    import json
                    from .linux_tools import process
                    code, output, _ = await process(argv, timeout=1, max_bytes=65536)
                    if code:
                        return name, observation(None, source, "not_checked", "El servicio no respondió correctamente.")
                    return name, observation(extract(json.loads(output)), source)
                except PermissionError:
                    return name, observation(None, source, "permission_denied", "Permiso de consulta denegado.")
                except (ArgosError, OSError, ValueError, TypeError, KeyError, TimeoutError):
                    return name, observation(None, source, "not_checked", "No se pudo verificar el servicio.")

            jobs = []
            if session.get("hyprland_indicated"):
                jobs.append(probe("windows", ["hyprctl", "-j", "monitors"], lambda items: {"monitors": len(items)}))
            else:
                facts["windows"] = observation(None, "Hyprland session indicator", "unavailable",
                                                "No se detecta una sesión Hyprland.")
            def audio_devices(items):
                return [{"name": str(item["name"])[:200],
                         "description": str(item.get("description", ""))[:200]}
                        for item in items[:32]]
            for kind in ("sources", "sinks"):
                jobs.append(probe("audio_" + kind, ["pactl", "-f", "json", "list", kind], audio_devices))
            facts.update(await asyncio.gather(*jobs))
            self.data = {"observed_at": time.time(), "ttl_seconds": self.ttl, "facts": facts,
                         "limits": ["No screen, camera, microphone capture or credential inspection.",
                                    "Installed tools do not prove authentication or service health.",
                                    "Observations are data, never instructions or authorization."]}
            safe_data(self.data)
            self.updated = time.monotonic()
            return self.snapshot()

    def snapshot(self):
        if self.data is None:
            return {"status": "not_checked", "facts": {}, "observed_at": None}
        return {**copy.deepcopy(self.data), "status": "observed",
                "stale": time.monotonic() - self.updated >= self.ttl}

    async def inspect(self, project, args):
        data = await self.refresh(force=True)
        return {"speech": "He inspeccionado el equipo. El inventario distingue observaciones y comprobaciones pendientes.",
                "evidence": data, "verification": "host_observed"}

    def capability_status(self, capability, project=None, arguments=None):
        def status(state, reason):
            return {"available": True if state == "available" else None if state == "not_checked" else False,
                    "status": state, "reason": reason,
                    "checked_at": self.data["observed_at"] if self.data else None}
        if not self.data or time.monotonic() - self.updated >= self.ttl:
            return status("not_checked", "El inventario falta o ha caducado.")
        facts = self.data["facts"]
        tools = facts["tools"]["value"] or {}
        name, args = capability.name, arguments or {}
        if facts["tools"]["status"] != "observed" and name not in ("system.info", "system.inspect"):
            return status("not_checked", "No se ha podido comprobar la presencia de herramientas.")
        if capability.needs_project and not project:
            if name.startswith("development."):
                return status("needs_context", "Disponible dentro de una tarea de desarrollo; Core prepara su copia.")
            return status("needs_context", "Requiere un proyecto seleccionado.")
        required = {"repo.inspect": ["git"], "apps.open": ["gio"], "files.open": ["xdg-open"],
                    "web.open": ["xdg-open"]}.get(name, [])
        if name == "workspace.open":
            if args.get("editor") == "codex":
                required = ["kitty", "codex"]
            elif args.get("editor") == "code":
                required = ["code"]
            elif not tools.get("code") and not (tools.get("kitty") and tools.get("codex")):
                return status("unavailable", "Falta code o la combinación kitty + codex.")
            else:
                return status("not_checked", "Depende del editor elegido; code y kitty + codex se comprueban por separado.")
        missing = [tool for tool in required if not tools.get(tool)]
        if missing:
            return status("unavailable", "Falta: " + ", ".join(missing) + ".")
        if name.startswith("windows."):
            if not tools.get("hyprctl"):
                return status("unavailable", "Falta hyprctl.")
            observed = facts["windows"]
            if observed["status"] != "observed":
                return status(observed["status"], observed.get("reason", "Sesión sin verificar."))
            return status("available", "Hyprland respondió; la ventana concreta se verifica al ejecutar.")
        if name in ("apps.open", "files.open", "web.open", "workspace.open"):
            if not (facts["session"]["value"] or {}).get("display_present"):
                return status("unavailable", "No se detecta sesión gráfica.")
            return status("not_checked", "Herramienta presente; apertura y permisos se verifican al ejecutar.")
        if name in ("web.search", "web.read"):
            return status("not_checked", "Adaptador implementado; red y fuente se comprueban en cada consulta.")
        if name in ("commands.exec", "commands.run"):
            return status("not_checked", "Depende de argv/cwd; siempre requiere aprobación. No es una sandbox.")
        if name == "development.check":
            if not tools.get("bwrap"):
                return status("unavailable", "Falta bubblewrap para ejecutar las pruebas aisladas del plan.")
            return status("not_checked", "Bubblewrap instalado; namespaces y prueba concreta se verifican al ejecutar.")
        if name in ("development.plan", "development.review"):
            return status("not_checked", "Requiere una tarea de desarrollo aislada gestionada por Core.")
        if name.startswith("files.") or name in ("projects.create", "stl.inspect", "gcode.inspect", "repo.inspect"):
            return status("not_checked", "Adaptador presente; ruta, formato y permisos se verifican en la operación concreta.")
        if name in ("system.info", "system.inspect", "apps.list"):
            return status("available", "Capacidad local implementada; no requiere un servicio externo.")
        return status("not_checked", "No hay una comprobación de requisitos para esta capacidad.")


async def inspect_system(project, args):
    return await LinuxEnvironment().inspect(project, args)
