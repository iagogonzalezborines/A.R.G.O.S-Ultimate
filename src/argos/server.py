import asyncio
import fcntl
import json
import os
import signal

from .core import Core
from .models import ArgosError
from .store import Store
from .voice import VoiceOutput


async def serve(directory, interpreter=None):
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if directory.resolve() in (directory.resolve().parent, __import__("pathlib").Path.home()):
        raise ArgosError("La carpeta de estado debe ser exclusiva de ARGOS.")
    directory.chmod(0o700)
    lock = (directory / "core.lock").open("a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        raise ArgosError("Ya hay un Core activo en esa carpeta.") from None
    socket = directory / "core.sock"
    store = Store(directory)
    core = Core(store, interpreter)
    core.voice = VoiceOutput()
    stopped = asyncio.Event()
    clients = set()
    sessions = asyncio.Semaphore(32)

    async def client(reader, writer):
        current = asyncio.current_task()
        clients.add(current)
        try:
            async with sessions:
                try:
                    line = await asyncio.wait_for(reader.readline(), 10)
                    message = json.loads(line)
                    result = await core.request(message)
                except ArgosError as error:
                    result = {"error": str(error)}
                except (KeyError, TypeError, ValueError, OSError, TimeoutError):
                    result = {"error": "Petición inválida o incompleta."}
                writer.write(json.dumps(result, ensure_ascii=False).encode() + b"\n")
                await writer.drain()
        except (ConnectionError, BrokenPipeError):
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass
            clients.discard(current)

    try:
        socket.unlink(missing_ok=True)
        await core.start()
        server = await asyncio.start_unix_server(client, str(socket), limit=65536)
        socket.chmod(0o600)
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stopped.set)
        async with server:
            await stopped.wait()
    finally:
        for client_task in list(clients):
            client_task.cancel()
        await asyncio.gather(*clients, return_exceptions=True)
        await core.voice.stop()
        await core.close()
        store.close()
        socket.unlink(missing_ok=True)
        lock.close()
