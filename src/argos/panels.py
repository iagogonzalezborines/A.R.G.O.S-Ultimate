"""Launch/focus ARGOS's own read-only windows without affecting background work."""
import asyncio
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from .models import ArgosError
from .linux_tools import process


class Panels:
    def __init__(self, directory):
        self.directory = directory
        self.lock = asyncio.Lock()
        self.children = {}

    async def windows(self):
        if not shutil.which("hyprctl"):
            return []
        try:
            code, output, _ = await process(["hyprctl", "clients", "-j"], timeout=2)
            return json.loads(output) if code == 0 else []
        except (ArgosError, OSError, ValueError, TimeoutError):
            return []

    async def dispatch(self, action, address, width=None, height=None):
        if not re.fullmatch(r"0x[0-9a-fA-F]+", address):
            raise ArgosError("Ventana de panel inválida.")
        selector = f'window="address:{address}"'
        commands = {
            "focus": (f"hl.dsp.focus({{{selector}}})", ["focuswindow", "address:" + address]),
            "raise": (f'hl.dsp.window.alter_zorder({{{selector},mode="top"}})',
                      ["alterzorder", "top,address:" + address]),
            "float": (f'hl.dsp.window.float({{{selector},action="set"}})', ["setfloating", "address:" + address]),
            "center": (f"hl.dsp.window.center({{{selector}}})", []),
        }
        if action == "resize":
            if type(width) is not int or type(height) is not int:
                raise ArgosError("Tamaño de panel inválido.")
            modern = f"hl.dsp.window.resize({{{selector},x={width},y={height},relative=false}})"
            legacy = ["resizewindowpixel", f"exact {width} {height},address:{address}"]
        elif action in commands:
            modern, legacy = commands[action]
        else:
            raise ArgosError("Acción de panel desconocida.")
        code, _, _ = await process(["hyprctl", "dispatch", modern], timeout=2)
        if code and legacy:  # Hyprland before its Lua dispatcher interface.
            code, _, _ = await process(["hyprctl", "dispatch", *legacy], timeout=2)
        return code == 0

    async def arrange(self, window):
        """Give a newly opened diagram room on its own monitor, without changing rules."""
        address = window.get("address", "")
        if not re.fullmatch(r"0x[0-9a-fA-F]+", address):
            return
        try:
            code, output, _ = await process(["hyprctl", "monitors", "-j"], timeout=2)
            monitors = json.loads(output) if code == 0 else []
            monitor = next((m for m in monitors if m["id"] == window.get("monitor")), None)
            if not monitor:
                return
            w, h = monitor["width"], monitor["height"]
            if monitor.get("transform", 0) % 2:
                w, h = h, w
            w, h = int(w / monitor.get("scale", 1)), int(h / monitor.get("scale", 1))
            width, height = min(1180, w - 60), min(780, h - 60)
            await self.dispatch("float", address)
            await self.dispatch("resize", address, width, height)
            if not await self.dispatch("center", address):
                x, y = monitor["x"] + (w - width) // 2, monitor["y"] + (h - height) // 2
                await process(["hyprctl", "dispatch", "movewindowpixel",
                               f"exact {x} {y},address:{address}"], timeout=2)
        except (ArgosError, OSError, ValueError, KeyError, TimeoutError):
            pass  # Other compositors and manual terminal launches still work.

    async def open(self, view, session):
        if view not in ("agents", "tasks"):
            raise ArgosError("Panel desconocido.")
        key = (view, session)
        identity = hashlib.sha256((str(self.directory.resolve()) + ":" + session).encode()).hexdigest()[:10]
        window_class = f"argos-{view}-{identity}"
        async with self.lock:
            for window in await self.windows():
                if window.get("class") == window_class:
                    address = window.get("address", "")
                    if re.fullmatch(r"0x[0-9a-fA-F]+", address):
                        try:
                            if await self.dispatch("focus", address):
                                raised = await self.dispatch("raise", address)
                                return {"view": view, "status": "focused" if raised else "requested"}
                        except (ArgosError, OSError, TimeoutError):
                            pass
            child = self.children.get(key)
            if child and child.poll() is None:
                return {"view": view, "status": "requested"}
            terminal = shutil.which("kitty")
            if not terminal:
                raise ArgosError("Falta kitty. Abre «argos monitor agents» o «argos monitor tasks» en una terminal.")
            executable = Path(__file__).resolve().parents[2] / "argos"
            child = subprocess.Popen([
                terminal, "--class", window_class,
                "--title", "ARGOS · " + ("AGENTES" if view == "agents" else "TAREAS"),
                "-o", "initial_window_width=128c", "-o", "initial_window_height=42c",
                "-o", "remember_window_size=no", "-o", "font_size=11",
                "-o", "background_opacity=1", "-o", "background=#0b1019",
                sys.executable, str(executable), "--state-dir", str(self.directory),
                "--session", session, "monitor", view],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, start_new_session=True)
            self.children[key] = child
            await asyncio.sleep(.15)
            if child.poll() is not None:
                raise ArgosError("No se pudo abrir la ventana de diagnóstico.")
            if shutil.which("hyprctl"):
                for _ in range(6):
                    window = next((w for w in await self.windows() if w.get("class") == window_class), None)
                    if window:
                        await self.arrange(window)
                        break
                    await asyncio.sleep(.08)
            return {"view": view, "status": "requested"}
