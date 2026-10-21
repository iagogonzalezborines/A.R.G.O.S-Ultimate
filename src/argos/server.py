import asyncio
import fcntl
import json
import os
import signal

from .core import Core
from .models import ArgosError
from .store import Store
from .voice import VoiceOutput


async def serve(directory, interpreter=None, voice_enabled=False, escalation_provider=None):
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
    from .host import LinuxEnvironment
    from pathlib import Path
    from .development import Development
    from .development_workspace import LinuxDevelopmentWorkspace
    development = Development(store, LinuxDevelopmentWorkspace(directory, Path(__file__).resolve().parents[2]))
    core = Core(store, interpreter, environment=LinuxEnvironment(), development=development,
                escalation_provider=escalation_provider)
    from .panels import Panels
    core.panels = Panels(directory)
    core.voice = VoiceOutput()
    voice_worker = warmup = None
    if voice_enabled:
        from .speech import Capture, Speech, VoiceWorker
        voice_worker = VoiceWorker()
        audio_directory = directory / "audio"
        audio_directory.mkdir(mode=0o700, exist_ok=True)
        for stale in audio_directory.glob("*.wav"):
            stale.unlink(missing_ok=True)
        core.speech = Speech(voice_worker, core.voice, audio_directory)
        core.capture = Capture(core, voice_worker, audio_directory)
        core.speech.language = store.setting("voice.language", "es")
        core.speech.automatic_language = store.setting("voice.language_mode", "auto") == "auto"
        core.capture.input_device = store.setting("voice.input_device")
        from .wake import WakeListener
        core.wake = WakeListener(core, voice_worker, audio_directory)
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
        server = await asyncio.start_unix_server(client, str(socket), limit=256000)
        socket.chmod(0o600)
        if voice_worker:
            warmup = asyncio.create_task(voice_worker.warmup(core.speech.language))
            if store.setting("voice.wake_enabled", False):
                await core.wake.configure(True, store.setting("voice.wake_project"),
                                          store.setting("voice.wake_session", "default"))
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stopped.set)
        async with server:
            await stopped.wait()
    finally:
        for client_task in list(clients):
            client_task.cancel()
        await asyncio.gather(*clients, return_exceptions=True)
        if core.wake:
            await core.wake.stop()
        if core.capture:
            await core.capture.cancel()
        if core.speech:
            await core.speech.stop()
        if warmup:
            warmup.cancel()
            await asyncio.gather(warmup, return_exceptions=True)
        if voice_worker:
            await voice_worker.close()
        await core.voice.stop()
        await core.close()
        store.close()
        socket.unlink(missing_ok=True)
        lock.close()
