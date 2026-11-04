"""Scoped MPRIS playback commands. No keystrokes or implicit player selection."""
import asyncio
import re
import shutil

from .linux_tools import process
from .models import ArgosError
from .security import public_text


async def players():
    if not shutil.which("playerctl"):
        raise ArgosError("Falta playerctl para controlar la reproducción.")
    code, out, _ = await process(["playerctl", "--list-all"], timeout=3, max_bytes=4096)
    if code:
        return []
    return [name for name in out.splitlines()[:16]
            if re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,160}", name)]


async def inspect_player(player):
    code, out, _ = await process(["playerctl", "--player=" + player, "metadata",
                                  "--format", "{{status}}\n{{title}}"], timeout=3, max_bytes=4096)
    status, separator, title = out.strip().partition("\n")
    if code or not separator or status not in ("Playing", "Paused", "Stopped") or not title:
        raise ArgosError("El reproductor no expone un vídeo o una canción identificable.")
    public_text(title, 1000)
    return {"player": player, "status": status, "title": title}


async def status(project, args):
    observed = []
    for name in await players():
        try:
            observed.append(await inspect_player(name))
        except ArgosError:
            continue
    return {"speech": "He consultado los reproductores disponibles.",
            "evidence": {"players": observed}, "verification": "media_observed"}


async def control(project, args):
    if args["action"] not in ("play", "pause"):
        raise ArgosError("Selecciona play o pause.")
    names = await players()
    # A family such as firefox is accepted only if it identifies one instance.
    matches = [n for n in names if n == args["player"] or n.startswith(args["player"] + ".")]
    if len(matches) != 1:
        raise ArgosError("El reproductor no está identificado de forma única. Consulta media.status.")
    name = matches[0]
    before = await inspect_player(name)
    if before["title"] != args["expected_title"]:
        raise ArgosError("El vídeo ha cambiado o no coincide. Consulta media.status antes de actuar.")
    desired = "Playing" if args["action"] == "play" else "Paused"
    if before["status"] != desired:
        code, _, _ = await process(["playerctl", "--player=" + name, args["action"]], timeout=3)
        if code:
            raise ArgosError("Firefox o el reproductor rechazó el control multimedia.")
    for attempt in range(6):
        after = await inspect_player(name)
        if after["title"] != before["title"]:
            raise ArgosError("El vídeo cambió durante la operación; no se puede confirmar el resultado.")
        if after["status"] == desired:
            return {"speech": "Reproducción confirmada." if desired == "Playing" else "Reproducción pausada.",
                    "evidence": after, "verification": "media_state_observed",
                    "limits": "Estado declarado por MPRIS; no certifica sonido audible ni selecciona resultados web."}
        if attempt < 5:
            await asyncio.sleep(.1)
    raise ArgosError("El comando se envió, pero el reproductor no confirmó el estado solicitado.")


def capabilities(C):
    return [C("media.status", "computer", "Observar títulos y estado de reproductores MPRIS, incluido Firefox", (), False, status),
            C("media.control", "computer", "Play/pause de un medio ya cargado; consultar media.status y copiar su título exacto antes",
              ("player", "action", "expected_title"), False, control, "routine")]
