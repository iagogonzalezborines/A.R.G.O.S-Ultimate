"""Session-owned PipeWire echo cancellation; no persistent audio configuration."""
import asyncio
import contextlib
import json
import shutil
import uuid

from .linux_tools import process
from .models import ArgosError


class EchoCancellation:
    def __init__(self):
        name = "argos-aec-" + uuid.uuid4().hex
        self.source, self.sink = name + "-source", name + "-sink"
        self.process = None
        self.active = False
        self.last_error = None

    async def start(self, device=None):
        """Publish private AEC nodes, or leave the caller in half-duplex mode."""
        await self.stop()
        self.last_error = None
        try:
            if not all(shutil.which(tool) for tool in ("pw-cli", "pw-dump", "pw-play", "pactl")):
                raise ArgosError("Faltan herramientas PipeWire.")
            if not device:
                code, device, _ = await process(["pactl", "get-default-source"], timeout=3)
                if code:
                    raise ArgosError("No hay micrófono predeterminado.")
                device = device.strip()
            code, sink, _ = await process(["pactl", "get-default-sink"], timeout=3)
            sink = sink.strip()
            if code or not device or not sink or device.startswith("argos-aec-") or sink.startswith("argos-aec-"):
                raise ArgosError("No hay dispositivos físicos disponibles.")
            # Freeze both targets before publishing virtual devices. Never change
            # system defaults or let a missing selected microphone fall back.
            args = {"library.name": "aec/libspa-aec-webrtc", "audio.rate": 48000,
                    "audio.channels": 1, "audio.position": ["MONO"],
                    "capture.props": {"target.object": device, "node.dont-fallback": True},
                    "playback.props": {"target.object": sink, "node.dont-fallback": True},
                    "source.props": {"node.name": self.source, "node.description": "ARGOS echo cancellation",
                                     "node.virtual": True, "priority.session": 0},
                    "sink.props": {"node.name": self.sink, "node.description": "ARGOS voice reference",
                                   "node.virtual": True, "priority.session": 0}}
            # pw-cli loads the module in its own process. Reaping that process
            # removes all its nodes, including after failed/cancelled setup.
            self.process = await asyncio.create_subprocess_exec(
                "pw-cli", "--monitor", "load-module", "libpipewire-module-echo-cancel",
                json.dumps(args).replace("#", "\\u0023"),
                stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL)
            async with asyncio.timeout(5):
                while self.process.returncode is None:
                    code, output, _ = await process(["pw-dump"], timeout=2, max_bytes=4 * 1024 * 1024)
                    nodes = {item.get("info", {}).get("props", {}).get("node.name")
                             for item in json.loads(output)} if not code else set()
                    if {self.source, self.sink, device, sink} <= nodes:
                        self.active = True
                        return True
                    await asyncio.sleep(.05)
                raise ArgosError("No se pudo cargar el cancelador de eco.")
        except (ArgosError, OSError, ValueError, TimeoutError):
            self.last_error = "Cancelación de eco no disponible; interrupción por voz desactivada."
            await self.stop()
            return False
        except BaseException:
            await self.stop()
            raise

    async def watch(self):
        await self.process.wait()
        self.active = False
        self.last_error = "Se perdió la cancelación de eco. Reactiva la escucha para reintentar."
        raise ArgosError(self.last_error)

    async def stop(self):
        self.active = False
        if self.process and self.process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), 2)
            except TimeoutError:
                with contextlib.suppress(ProcessLookupError):
                    self.process.kill()
                await self.process.wait()
        self.process = None
