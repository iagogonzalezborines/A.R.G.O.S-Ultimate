import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

from . import __version__
from .models import ArgosError, Status
from .transport import call, state_directory


def parser():
    p = argparse.ArgumentParser(description="ARGOS — Core local y consola de voz")
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument("--state-dir", type=Path, default=state_directory())
    p.add_argument("--json", action="store_true")
    p.add_argument("--session", default="default")
    p.add_argument("--request-id", default=None, help="Reutiliza este ID al reintentar la misma petición")
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("serve", help="Ejecutar Core; no muestra registros en la consola")
    s.add_argument("--ollama-model", help="Opcional: modelo local ya instalado; no descarga nada")
    sub.add_parser("console", help="Esfera ASCII; Ctrl-C solo cierra la visualización")
    s = sub.add_parser("say", help="Entrada textual para desarrollo; mismo punto de entrada que futuro STT")
    s.add_argument("text")
    s.add_argument("--project")
    for name in ("agents", "tasks", "projects"):
        sub.add_parser(name)
    s = sub.add_parser("add-project")
    s.add_argument("name")
    s.add_argument("path")
    s = sub.add_parser("run", help="Ejecutar una capacidad registrada")
    s.add_argument("capability")
    s.add_argument("--project")
    s.add_argument("--file")
    s.add_argument("--wait", action="store_true")
    for name in ("task", "cancel", "resume", "reply"):
        s = sub.add_parser(name)
        s.add_argument("task_id")
        if name == "reply":
            s.add_argument("text")
    s = sub.add_parser("play-wav", help="Salida PCM real y amplitud para la esfera; no es TTS")
    s.add_argument("path")
    sub.add_parser("stop-speech")
    s = sub.add_parser("doctor")
    s.add_argument("--codex", action="store_true", help="Comprobar App Server sin llamar al modelo")
    sub.add_parser("contract", help="Mostrar contrato ARGOS cargado en ejecución")
    return p


async def execute(args):
    if args.command == "serve":
        from .server import serve
        from .providers import OllamaInterpreter
        provider = OllamaInterpreter(args.ollama_model) if args.ollama_model else None
        await serve(args.state_dir, provider)
        return
    if args.command == "console":
        from .console import console
        await console(args.state_dir)
        return
    if args.command == "contract":
        from .agents import contract
        print(contract())
        return
    if args.command == "doctor":
        import platform
        import shutil
        result = {"version": __version__, "python": platform.python_version(),
                  "platform": platform.system(), "runtime_dependencies": [],
                  "audio_player": shutil.which("pw-play") or shutil.which("aplay"),
                  "voice_input": "not_connected", "tts": "not_connected"}
        if args.codex:
            from .codex_probe import probe
            result["codex"] = await probe()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    methods = {"projects": "projects.list", "add-project": "projects.add",
               "play-wav": "voice.play", "stop-speech": "voice.stop"}
    message = {"method": methods.get(args.command, args.command), "session": args.session,
               "request_id": args.request_id or uuid.uuid4().hex}
    for name in ("text", "project", "task_id", "name", "path", "capability"):
        if hasattr(args, name) and getattr(args, name) is not None:
            message[name] = getattr(args, name)
    if args.command == "run":
        message["arguments"] = {"file": args.file} if args.file else {}
    result = await call(args.state_dir, message)
    if args.command == "run" and args.wait and result.get("task_id"):
        for _ in range(600):
            task = (await call(args.state_dir, {"method": "task", "session": args.session,
                                               "task_id": result["task_id"]}))["data"]
            if task["status"] not in (Status.QUEUED, Status.RUNNING):
                result["data"] = task
                result["speech"] = (task["result"] or {}).get("speech") or task["question"] or task["status"]
                result["kind"] = task["status"].lower()
                break
            await asyncio.sleep(0.1)
        else:
            raise ArgosError("La tarea sigue en segundo plano. Consulta su estado.")
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result["speech"])
        if result.get("task_id"):
            print("Task:", result["task_id"])
        if args.command in ("task", "tasks", "agents", "projects") and result.get("data") is not None:
            print(json.dumps(result["data"], ensure_ascii=False, indent=2))
    if result.get("kind") == "failed":
        return 1
    return 0


def main():
    args = parser().parse_args()
    try:
        code = asyncio.run(execute(args))
    except KeyboardInterrupt:
        code = 0
    except (ArgosError, FileNotFoundError) as error:
        print(f"ARGOS: {error}", file=sys.stderr)
        code = 1
    raise SystemExit(code or 0)
