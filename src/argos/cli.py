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
    s.add_argument("--codex", action="store_true", help="Conectar Codex con tu sesión ChatGPT")
    s.add_argument("--voice", action="store_true", help="Whisper y Pocket TTS locales ya instalados")
    s = sub.add_parser("console", help="Espacio: hablar/enviar. Escape: silencio. Q: cerrar esfera.")
    s.add_argument("--project", help="Proyecto seleccionado para las peticiones de voz")
    s = sub.add_parser("start", help="Abrir ARGOS con Codex y voz en una consola independiente")
    s.add_argument("--project")
    s = sub.add_parser("say", help="Entrada textual para desarrollo; mismo punto de entrada que futuro STT")
    s.add_argument("text")
    s.add_argument("--project")
    s.add_argument("--speak", action="store_true")
    for name in ("agents", "tasks", "projects"):
        sub.add_parser(name)
    s = sub.add_parser("add-project")
    s.add_argument("name")
    s.add_argument("path")
    s = sub.add_parser("run", help="Ejecutar una capacidad registrada")
    s.add_argument("capability")
    s.add_argument("--project")
    s.add_argument("--file")
    s.add_argument("--args", type=json.loads, default={}, help="Objeto JSON con argumentos de la capacidad")
    s.add_argument("--wait", action="store_true")
    for name in ("task", "cancel", "resume", "reply", "review", "approve"):
        s = sub.add_parser(name)
        s.add_argument("task_id")
        if name == "reply":
            s.add_argument("text")
        if name == "approve":
            s.add_argument("fingerprint", help="Huella completa mostrada por review")
    s = sub.add_parser("register-command", help="Registrar argv exactos; no ejecuta el comando")
    s.add_argument("--project", required=True)
    s.add_argument("name")
    s.add_argument("argv", nargs=argparse.REMAINDER)
    sub.add_parser("voice-status")
    sub.add_parser("voice-inputs", help="Listar micrófonos disponibles")
    s = sub.add_parser("voice-config", help="Guardar idioma y micrófono de ARGOS")
    s.add_argument("--language", choices=("auto", "es", "en"))
    s.add_argument("--input-device", help="ID mostrado por voice-inputs")
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
        if args.codex and args.ollama_model:
            raise ArgosError("Selecciona un solo proveedor.")
        provider = OllamaInterpreter(args.ollama_model) if args.ollama_model else None
        if args.codex:
            from .codex import Codex
            provider = Codex(args.state_dir)
        await serve(args.state_dir, provider, voice_enabled=args.voice)
        return
    if args.command == "start":
        from .launcher import start
        await start(args.state_dir, args.project)
        print("ARGOS abierto. Espacio: hablar/enviar · Escape: silencio · Q: cerrar consola.")
        return
    if args.command == "console":
        from .console import console
        await console(args.state_dir, args.project)
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
                  "audio_player": shutil.which("pw-play") or shutil.which("aplay")}
        from .speech import VOICE_PYTHON
        result["voice_environment_installed"] = VOICE_PYTHON.exists()
        try:
            result["running_voice"] = (await call(args.state_dir, {"method": "voice.state"}))["data"]
        except ArgosError:
            result["core"] = "not_running"
        if args.codex:
            from .codex_probe import probe
            result["codex"] = await probe()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    methods = {"projects": "projects.list", "add-project": "projects.add",
               "play-wav": "voice.play", "stop-speech": "voice.stop",
               "voice-status": "voice.state", "voice-inputs": "voice.inputs",
               "voice-config": "voice.configure", "review": "task", "register-command": "commands.register"}
    message = {"method": methods.get(args.command, args.command), "session": args.session,
               "request_id": args.request_id or uuid.uuid4().hex}
    for name in ("text", "project", "task_id", "name", "path", "capability", "fingerprint", "speak", "argv",
                 "language", "input_device"):
        if hasattr(args, name) and getattr(args, name) is not None:
            message[name] = getattr(args, name)
    if args.command == "run":
        if not isinstance(args.args, dict):
            raise ArgosError("--args necesita un objeto JSON.")
        message["arguments"] = {**args.args, **({"file": args.file} if args.file else {})}
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
        if args.command in ("task", "tasks", "agents", "projects", "review", "voice-status", "voice-config",
                            "voice-inputs", "register-command") and result.get("data") is not None:
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
