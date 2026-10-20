"""Read-only compatibility probe. Does not create a thread or invoke a model."""
import asyncio
import json
import shutil
from pathlib import Path

from .models import ArgosError


def find_binary():
    binary = shutil.which("codex")
    if binary:
        return binary
    for root in (".vscode-oss", ".vscode"):
        candidates = sorted((Path.home() / root / "extensions").glob(
            "openai.chatgpt-*/bin/linux-x86_64/codex"), key=lambda p: p.stat().st_mtime, reverse=True)
        if candidates:
            return str(candidates[0])
    return None


async def probe():
    binary = find_binary()
    if not binary:
        return {"available": False, "reason": "Codex no está instalado."}
    proc = await asyncio.create_subprocess_exec(
        binary, "app-server", "--listen", "stdio://",
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL, limit=1024 * 1024)

    async def request(identifier, method, params):
        proc.stdin.write(json.dumps({"id": identifier, "method": method, "params": params}).encode() + b"\n")
        await proc.stdin.drain()
        while True:
            line = await asyncio.wait_for(proc.stdout.readline(), 15)
            if not line:
                raise ArgosError("Codex cerró la conexión.")
            data = json.loads(line)
            if data.get("id") == identifier:
                if "error" in data:
                    raise ArgosError("La versión instalada no acepta la comprobación.")
                return data.get("result", {})

    try:
        await request(1, "initialize", {
            "clientInfo": {"name": "argos_core", "title": "ARGOS", "version": "0.1.0"},
            "capabilities": {"experimentalApi": False}})
        proc.stdin.write(b'{"method":"initialized","params":{}}\n')
        await proc.stdin.drain()
        account = (await request(2, "account/read", {"refreshToken": False})).get("account")
        # Intentionally discard email, account identifiers and plan details.
        kind = account.get("type") if isinstance(account, dict) else None
        return {"available": True, "transport": "app-server/stdio", "auth_type": kind,
                "subscription_login": kind == "chatgpt",
                "inference_tested": False,
                "reason": "Handshake comprobado sin consultar el modelo."}
    except (OSError, ValueError, TimeoutError, ArgosError):
        return {"available": False, "reason": "No se pudo validar App Server."}
    finally:
        if proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), 3)
            except TimeoutError:
                proc.kill()
                await proc.wait()
