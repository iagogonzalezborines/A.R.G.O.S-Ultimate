"""Narrow native-messaging bridge: select and play a YouTube video in Firefox."""
import asyncio
import contextlib
import fcntl
import json
import os
from pathlib import Path
import struct
import sys
import time
import uuid

from .models import ArgosError
from .security import public_text, safe_data
from .transport import state_directory

HOST = 'argos.firefox'
EXTENSION = 'firefox@argos.local'


def socket_path(directory=None):
    return (directory or state_directory()) / 'firefox.sock'


def validate_request(request):
    if not isinstance(request, dict) or set(request) != {'action', 'query'} or request['action'] != 'play':
        raise ArgosError('Solicitud de navegador no admitida.')
    if not isinstance(request['query'], str):
        raise ArgosError('La búsqueda debe ser texto.')
    public_text(request['query'], 300)
    if not request['query'].strip():
        raise ArgosError('Indica el título y artista del vídeo.')
    return request


async def play(project, args, directory=None):
    request = validate_request({'action': 'play', 'query': args['query']})
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_unix_connection(str(socket_path(directory)), limit=65536), 2)
    except (OSError, TimeoutError):
        raise ArgosError('La extensión ARGOS de Firefox no está conectada. Cárgala desde about:debugging.') from None
    try:
        writer.write(json.dumps(request).encode() + b'\n')
        await writer.drain()
        raw = await asyncio.wait_for(reader.readline(), 55)
        result = json.loads(raw)
        safe_data(result)
        if result.get('status') != 'playing':
            messages = {
                'autoplay_blocked': 'Firefox bloqueó el inicio. Permite audio y vídeo en la configuración de reproducción automática de YouTube.',
                'no_match': 'No encontré un resultado cuyo título coincida con la canción y artista solicitados.',
                'page_blocked': 'YouTube necesita atención en Firefox: puede haber un aviso de consentimiento o inicio de sesión.',
                'busy': 'Firefox está atendiendo otra petición de ARGOS.',
                'timeout': 'No pude confirmar que el vídeo solicitado empezase a reproducirse.',
            }
            raise ArgosError(messages.get(result.get('status'), 'No se pudo completar la reproducción en Firefox.'))
        title, url = result.get('title'), result.get('url')
        import re
        if (not isinstance(title, str) or not title.strip() or len(title) > 1000
                or not isinstance(url, str) or not re.fullmatch(r'https://www\.youtube\.com/watch\?v=[A-Za-z0-9_-]{11}', url)):
            raise ArgosError('Firefox devolvió evidencia de reproducción inválida.')
        return {'speech': 'Reproducción del vídeo confirmada.', 'evidence': {'title': title, 'url': url},
                'verification': 'browser_video_advancing',
                'limits': 'Vídeo no pausado y tiempo avanzando en la página; no certifica sonido físico.'}
    except (ValueError, TimeoutError, ConnectionError):
        raise ArgosError('Se perdió la conexión con Firefox; no se confirma reproducción.') from None
    finally:
        writer.close()
        await writer.wait_closed()


def capabilities(C):
    return [C('browser.play', 'computer', 'Buscar título/artista en YouTube, seleccionar coincidencia y verificar reproducción en Firefox; requiere extensión ARGOS',
              ('query',), False, play, 'routine')]


def setup(directory):
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    source = Path(__file__).resolve().parents[2]
    wrapper = directory / 'firefox-native-host'
    # Python literals, not shell interpolation. The interpreter path is fixed by setup.
    wrapper.write_text('#!' + sys.executable + '\nimport sys\n'
                       + 'sys.path.insert(0, ' + repr(str(source / 'src')) + ')\n'
                       + 'from pathlib import Path\nfrom argos.firefox import native_main\n'
                       + 'native_main(Path(' + repr(str(directory.resolve())) + '))\n')
    wrapper.chmod(0o700)
    manifest = {'name': HOST, 'description': 'ARGOS scoped YouTube playback', 'path': str(wrapper.resolve()),
                'type': 'stdio', 'allowed_extensions': [EXTENSION]}
    # Firefox supports the legacy and XDG per-user configuration layouts.
    roots = [Path.home() / '.mozilla', Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'mozilla']
    for root in roots:
        folder = root / 'native-messaging-hosts'
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (HOST + '.json')
        path.write_text(json.dumps(manifest) + '\n'); path.chmod(0o600)
    return {'extension_manifest': str(source / 'integrations/firefox/manifest.json'),
            'next': 'Firefox: about:debugging#/runtime/this-firefox > Load Temporary Add-on > select manifest.json',
            'scope': 'YouTube only; temporary extension lasts until Firefox restarts.'}


async def native_serve(directory):
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = (directory / 'firefox.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        return
    path = socket_path(directory)
    path.unlink(missing_ok=True)
    pending = {}
    input_reader = asyncio.StreamReader(limit=65536)
    transport, _ = await asyncio.get_running_loop().connect_read_pipe(
        lambda: asyncio.StreamReaderProtocol(input_reader), sys.stdin.buffer)

    def send(message):
        data = json.dumps(message).encode()
        sys.stdout.buffer.write(struct.pack('=I', len(data)) + data)
        sys.stdout.buffer.flush()

    async def accept(reader, writer):
        identifier = None
        try:
            request = validate_request(json.loads(await asyncio.wait_for(reader.readline(), 3)))
            if pending:
                result = {'status': 'busy'}
            else:
                identifier = uuid.uuid4().hex
                future = asyncio.get_running_loop().create_future()
                pending[identifier] = future
                send({**request, 'id': identifier, 'deadline': int(time.time() * 1000) + 45000})
                disconnected = asyncio.create_task(reader.read(1))
                try:
                    done, _ = await asyncio.wait((future, disconnected), timeout=48, return_when=asyncio.FIRST_COMPLETED)
                    if future in done:
                        result = future.result()
                    else:
                        send({'action': 'cancel', 'id': identifier})
                        result = {'status': 'timeout'}
                finally:
                    disconnected.cancel()
                    await asyncio.gather(disconnected, return_exceptions=True)
            writer.write(json.dumps(result).encode() + b'\n')
            await writer.drain()
        except (ArgosError, ValueError, OSError, TimeoutError):
            pass
        finally:
            if identifier:
                pending.pop(identifier, None)
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_unix_server(accept, path=str(path), limit=8192)
    path.chmod(0o600)
    try:
        while True:
            size = struct.unpack('=I', await input_reader.readexactly(4))[0]
            if not 0 < size <= 16384:
                break
            data = json.loads(await input_reader.readexactly(size))
            safe_data(data)
            if not isinstance(data, dict):
                break
            future = pending.get(data.get('id'))
            if future and not future.done():
                future.set_result({k: data[k] for k in ('status', 'title', 'url') if k in data})
    except (asyncio.IncompleteReadError, ValueError, ArgosError, OSError):
        pass
    finally:
        for future in pending.values():
            if not future.done():
                future.set_result({'status': 'disconnected'})
        server.close(); await server.wait_closed()
        transport.close(); path.unlink(missing_ok=True); lock.close()


def native_main(directory):
    with contextlib.suppress(BrokenPipeError, KeyboardInterrupt):
        asyncio.run(native_serve(directory))
