"""Read-only compatibility probe. Does not create a thread or invoke a model."""
import asyncio
import json
import shutil

from .models import ArgosError


async def probe():
    binary = shutil.which("codex")
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
                "inference_connected": False,
                "reason": "Handshake comprobado. El bridge de ejecución Codex aún no está conectado."}
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
