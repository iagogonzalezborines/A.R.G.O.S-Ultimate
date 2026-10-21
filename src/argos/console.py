"""The normal Linux surface: one ASCII sphere, no task log or chat transcript."""
import asyncio
import math
import shutil
import sys
import time
import os
import termios
import tty

from .models import ArgosError
from .transport import call


def frame(width, height, level=0.0, phase=0.0):
    width, height = max(12, min(width, 120)), max(6, min(height, 40))
    level = max(0.0, min(1.0, level))
    radius = min(width / 4.0, height / 2.8) * (0.75 + 0.23 * math.sqrt(level))
    center_x = (width - 1) / 2
    center_y = (height - 1) / 2 + math.sin(phase * 0.6) * 0.4
    light = (-0.45, -0.5, 0.74)
    palette = " .:-=+*#%@"
    rows = []
    for y in range(height):
        row = []
        for x in range(width):
            nx, ny = (x - center_x) / (radius * 2), (y - center_y) / radius
            norm = nx * nx + ny * ny
            if norm > 1:
                row.append(" ")
                continue
            nz = math.sqrt(1 - norm)
            shade = max(0.08, nx * light[0] + ny * light[1] + nz * light[2])
            ripple = 0.05 * level * math.sin(10 * ny + phase * 8)
            row.append(palette[min(len(palette) - 1, max(1, int((shade + ripple) * 9)))])
        rows.append("".join(row))
    return "\n".join(rows)


async def console(directory, project=None):
    if not sys.stdout.isatty():
        raise ArgosError("La esfera necesita una terminal interactiva.")
    # Check connection before entering alternate screen.
    data = (await call(directory, {"method": "voice.state"}))["data"]
    await call(directory, {"method": "voice.prepare", "project": project})
    keys = asyncio.Queue()
    loop = asyncio.get_running_loop()
    fd = sys.stdin.fileno()
    settings = termios.tcgetattr(fd)
    tty.setcbreak(fd)
    loop.add_reader(fd, lambda: keys.put_nowait(os.read(fd, 16)))
    sys.stdout.write("\x1b[?1049h\x1b[?25l")
    try:
        while True:
            now = time.monotonic()
            while not keys.empty():
                key = keys.get_nowait()
                if b"q" in key.lower():
                    return
                if b"\x1b" in key:
                    await call(directory, {"method": "voice.stop"})
                elif b" " in key:
                    try:
                        await call(directory, {"method": "voice.toggle", "project": project})
                    except ArgosError:
                        # Capture keeps the error in voice.state; preserve the sphere.
                        pass
            data = (await call(directory, {"method": "voice.state"}))["data"]
            width, height = shutil.get_terminal_size((80, 24))
            screen = frame(width, max(6, height - 1), data["level"], now)
            color = {"listening": "32", "thinking": "33", "speaking": "96", "error": "31"}.get(data["state"], "36")
            sys.stdout.write("\x1b[H\x1b[" + color + "m" + screen + "\x1b[0m\x1b[J")
            sys.stdout.flush()
            await asyncio.sleep(max(0, 0.1 - (time.monotonic() - now)))
    finally:
        loop.remove_reader(fd)
        termios.tcsetattr(fd, termios.TCSADRAIN, settings)
        sys.stdout.write("\x1b[0m\x1b[?25h\x1b[?1049l")
        sys.stdout.flush()
        if data.get("state") == "listening" and not data.get("wake_enabled", False):
            try:
                await call(directory, {"method": "voice.stop"})
            except ArgosError:
                pass
