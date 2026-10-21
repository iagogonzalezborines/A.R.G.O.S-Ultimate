"""Host filesystem operations, explicit paths and optimistic content versions.

Relative paths use a selected project; absolute paths need no registration.
Credentials and special devices never become provider context. Components are
opened without following symlinks, including absolute paths.
"""
import codecs
import ctypes
import errno
import hashlib
import json
import os
import re
import shutil
import stat
import uuid
from pathlib import Path

from .models import ArgosError
from .security import public_text

PAGE = 32000


def path_for(project, value):
    path = Path(value).expanduser()
    if ".." in path.parts:
        raise ArgosError("Usa una ruta absoluta explícita, sin componentes '..'.")
    if not path.is_absolute():
        if not project:
            raise ArgosError("Indica una ruta absoluta o selecciona un proyecto.")
        path = Path(project["root"]) / path
    for part in path.parts:
        if (part in (".ssh", ".gnupg", ".aws", ".azure", ".kube", ".codex")
                or part == ".env" or part.startswith(".env.")
                or re.search(r"(?:credential|secret|password|token|private[_-]?key)", part, re.I)):
            raise ArgosError("La ruta contiene credenciales o configuración privada protegida.")
    if path.suffix.lower() in (".pem", ".key", ".p12", ".pfx", ".sqlite", ".db"):
        raise ArgosError("Ese formato está protegido del acceso del agente.")
    if path.parts[:2] in (("/", "proc"), ("/", "sys"), ("/", "dev")):
        raise ArgosError("Los dispositivos y sistemas de archivos virtuales no son documentos.")
    return path


def open_directory(path):
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = nxt
        return fd
    except BaseException:
        os.close(fd)
        raise


def open_file(path):
    parent = open_directory(path.parent)
    try:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    finally:
        os.close(parent)
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise ArgosError("Se requiere un archivo normal.")
    return os.fdopen(fd, "rb")


def digest_path(path):
    """Fingerprint regular files or a complete directory tree; reject links."""
    parent = open_directory(path.parent)
    try:
        try:
            info = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            return ""
    finally:
        os.close(parent)
    digest = hashlib.sha256()
    if stat.S_ISREG(info.st_mode):
        with open_file(path) as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
    elif stat.S_ISDIR(info.st_mode):
        fd = open_directory(path)
        try:
            for name in sorted(os.listdir(fd)):
                child = path_for(None, str(path / name))
                digest.update(name.encode() + b"\0" + digest_path(child).encode() + b"\0")
        finally:
            os.close(fd)
        digest.update(b"directory")
    else:
        raise ArgosError("No se operan enlaces simbólicos ni archivos especiales.")
    return digest.hexdigest()


def check_version(path, expected):
    actual = digest_path(path)
    if actual != expected:
        raise ArgosError("La ruta ha cambiado desde su revisión. Revisa de nuevo la operación.")
    return actual


def number(value, maximum=None):
    if not isinstance(value, str) or not value.isascii() or not value.isdigit() or len(value) > 16:
        raise ArgosError("El desplazamiento debe ser un entero no negativo escrito como texto.")
    result = int(value)
    if maximum is not None and result > maximum:
        raise ArgosError("El tamaño de página excede el límite.")
    return result


def outcome(speech, evidence, verification):
    return {"speech": speech, "evidence": evidence, "verification": verification}


async def files_stat(project, args):
    path = path_for(project, args["path"])
    digest = digest_path(path)
    return outcome("Ruta inspeccionada.", {"path": str(path), "exists": bool(digest),
                   "sha256": digest, "directory": path.is_dir() if digest else False,
                   "bytes": path.stat().st_size if digest else 0}, "metadata_observed")


async def files_list(project, args):
    path = path_for(project, args["path"])
    offset = number(args.get("offset", "0"))
    fd = open_directory(path)
    try:
        entries = []
        for name in sorted(os.listdir(fd)):
            try:
                path_for(None, str(path / name))
            except ArgosError:
                continue
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if stat.S_ISLNK(info.st_mode):
                continue
            entries.append({"name": name, "directory": stat.S_ISDIR(info.st_mode), "bytes": info.st_size})
    finally:
        os.close(fd)
    page = entries[offset:offset + 150]
    result = outcome(f"Hay {len(page)} entradas en esta página.", page, "directory_observed")
    result.update(path=str(path), total=len(entries),
                  next_offset=str(offset + len(page)) if offset + len(page) < len(entries) else None)
    return result


def read_page(path, offset, limit):
    digest, decoder = hashlib.sha256(), codecs.getincrementaldecoder("utf-8")()
    position, content, tail = 0, [], ""
    with open_file(path) as file:
        while True:
            data = file.read(32768)
            digest.update(data)
            text = decoder.decode(data, final=not data)
            # Screen the entire file, including secrets crossing chunk boundaries.
            public_text(tail + text, 66000)
            tail = (tail + text)[-32768:]
            lo, hi = max(0, offset - position), min(len(text), offset + limit - position)
            if hi > lo:
                content.append(text[lo:hi])
            position += len(text)
            if not data:
                break
    return "".join(content), digest.hexdigest(), position


async def files_read(project, args):
    path = path_for(project, args["file"])
    offset = number(args.get("offset", "0"))
    limit = number(args.get("limit", str(PAGE)), PAGE)
    if not limit:
        raise ArgosError("La página debe tener al menos un carácter.")
    content, digest, total = read_page(path, offset, limit)
    expected = args.get("expected_sha256", "")
    if expected and expected != digest:
        raise ArgosError("El archivo ha cambiado entre páginas.")
    return outcome(f"He leído {path.name}.", {"file": str(path), "sha256": digest, "content": content,
                   "offset": str(offset), "total_characters": total,
                   "next_offset": str(offset + len(content)) if offset + len(content) < total else None}, "file_read")


async def files_write(project, args):
    return await edit(project, args, replace=True)


async def files_patch(project, args):
    return await edit(project, args, replace=False)


async def edit(project, args, replace):
    path = path_for(project, args["file"])
    public_text(args["content"], 64000)
    old = check_version(path, args["expected_sha256"])
    start, count = (0, 0) if replace else (number(args["offset"]), number(args["delete_count"]))
    if old:
        # Prevent existing secrets entering the model and validate UTF-8 before editing.
        _, _, length = read_page(path, 0, 0)
        if not replace and start + count > length:
            raise ArgosError("El tramo está fuera del archivo.")
    elif start or count:
        raise ArgosError("Un archivo nuevo empieza en el desplazamiento cero.")
    parent = open_directory(path.parent)
    temporary = ".argos-write-" + uuid.uuid4().hex
    try:
        fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600, dir_fd=parent)
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as output:
            if replace or not old:
                output.write(args["content"])
            else:
                with open_file(path) as raw:
                    import io
                    with io.TextIOWrapper(raw, encoding="utf-8", newline="") as source:
                        remaining = start
                        while remaining:
                            part = source.read(min(32768, remaining))
                            if not part:
                                raise ArgosError("El archivo cambió mientras se preparaba el parche.")
                            output.write(part)
                            remaining -= len(part)
                        output.write(args["content"])
                        remaining = count
                        while remaining:
                            part = source.read(min(32768, remaining))
                            if not part:
                                raise ArgosError("El archivo cambió mientras se preparaba el parche.")
                            remaining -= len(part)
                        shutil.copyfileobj(source, output, 32768)
            output.flush()
            os.fsync(output.fileno())
        if old:
            os.chmod(temporary, path.stat().st_mode & 0o777, dir_fd=parent)
        proposed = path.parent / temporary
        # Validate joins too (an insertion can construct a credential pattern).
        _, intended, _ = read_page(proposed, 0, 0)
        check_version(path, args["expected_sha256"])
        os.rename(temporary, path.name, src_dir_fd=parent, dst_dir_fd=parent)
        os.fsync(parent)
    finally:
        try:
            os.unlink(temporary, dir_fd=parent)
        except FileNotFoundError:
            pass
        os.close(parent)
    digest = digest_path(path)
    if digest != intended:
        raise ArgosError("No se ha podido verificar el contenido escrito.")
    return outcome(f"He guardado {path.name}.", {"file": str(path), "sha256": digest}, "content_verified")


async def files_mkdir(project, args):
    path = path_for(project, args["path"])
    # Create one level per operation: the exact parent and scope stay reviewable.
    parent = open_directory(path.parent)
    try:
        os.mkdir(path.name, 0o755, dir_fd=parent)
        os.fsync(parent)
    finally:
        os.close(parent)
    return outcome("Directorio creado.", {"path": str(path)}, "directory_created")


def rename_no_replace(source, destination):
    src, dst = open_directory(source.parent), open_directory(destination.parent)
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        result = libc.renameat2(src, os.fsencode(source.name), dst, os.fsencode(destination.name), 1)
        if result:
            error = ctypes.get_errno()
            if error == errno.EXDEV:
                raise ArgosError("Entre sistemas de archivos, copia primero y borra después de verificar.")
            raise OSError(error, os.strerror(error))
        os.fsync(src)
        os.fsync(dst)
    finally:
        os.close(src)
        os.close(dst)


async def files_move(project, args):
    source, destination = path_for(project, args["source"]), path_for(project, args["destination"])
    if not check_version(source, args["expected_sha256"]):
        raise ArgosError("El origen no existe.")
    rename_no_replace(source, destination)
    digest = check_version(destination, args["expected_sha256"])
    return outcome("Ruta movida.", {"source": str(source), "destination": str(destination),
                   "sha256": digest}, "move_verified")


async def files_copy(project, args):
    source, destination = path_for(project, args["source"]), path_for(project, args["destination"])
    expected = args["expected_sha256"]
    if not check_version(source, expected):
        raise ArgosError("El origen no existe.")
    parent = open_directory(destination.parent)
    os.close(parent)
    temporary = destination.parent / (".argos-copy-" + uuid.uuid4().hex)
    try:
        if source.is_dir():
            # The full digest rejects links/special files and protected paths first.
            shutil.copytree(source, temporary, symlinks=True)
        else:
            with open_file(source) as src, temporary.open("xb") as dst:
                shutil.copyfileobj(src, dst, 1024 * 1024)
                dst.flush()
                os.fsync(dst.fileno())
            temporary.chmod(source.stat().st_mode & 0o777)
        check_version(source, expected)
        check_version(temporary, expected)
        rename_no_replace(temporary, destination)
    finally:
        if temporary.is_dir():
            shutil.rmtree(temporary)
        else:
            temporary.unlink(missing_ok=True)
    return outcome("Copia verificada.", {"source": str(source), "destination": str(destination),
                   "sha256": expected}, "copy_verified")


async def files_delete(project, args):
    source = path_for(project, args["path"])
    if not source.name or source == Path.home():
        raise ArgosError("Selecciona una ruta concreta para borrar.")
    if not check_version(source, args["expected_sha256"]):
        raise ArgosError("La ruta no existe.")
    # Same filesystem, atomic rename, no irreversible recursive removal.
    parent = open_directory(source.parent)
    try:
        try:
            os.mkdir(".argos-trash", 0o700, dir_fd=parent)
        except FileExistsError:
            pass
    finally:
        os.close(parent)
    trash = source.parent / ".argos-trash"
    fd = open_directory(trash)
    os.close(fd)
    destination = trash / (uuid.uuid4().hex + "-" + source.name)
    result = await files_move(None, {"source": str(source), "destination": str(destination),
                                   "expected_sha256": args["expected_sha256"]})
    result["speech"] = "Ruta retirada a la papelera de ARGOS. Se puede restaurar con files.move."
    result["verification"] = "trash_verified"
    return result


async def files_open(project, args):
    from .linux_tools import process
    path = path_for(project, args["path"])
    if path.suffix.lower() in (".desktop", ".sh", ".exe", ".appimage", ".py", ".js"):
        raise ArgosError("No se abren ejecutables como documentos.")
    if path.is_dir():
        fd = open_directory(path)
        os.close(fd)
    else:
        with open_file(path):
            pass
    code, _, _ = await process(["xdg-open", str(path)])
    if code:
        raise ArgosError("No se pudo abrir la ruta.")
    return outcome("He solicitado abrir la ruta.", {"path": str(path)}, "open_dispatched")


async def projects_create(project, args):
    public_text(args["name"], 80)
    return await files_mkdir(project, {"path": args["path"]})


async def workspace_open(project, args):
    import asyncio
    if args["editor"] not in ("code", "codex"):
        raise ArgosError("El editor debe ser code o codex.")
    path = path_for(project, args["path"])
    fd = open_directory(path)
    os.close(fd)
    # Launch deliberately, with a reviewed cwd; no generated shell program.
    argv = ["code", "--new-window", str(path)] if args["editor"] == "code" else [
        "kitty", "--directory", str(path), "codex", "-C", str(path)]
    proc = await asyncio.create_subprocess_exec(*argv, cwd=str(path), start_new_session=True,
                                               stdin=asyncio.subprocess.DEVNULL,
                                               stdout=asyncio.subprocess.DEVNULL,
                                               stderr=asyncio.subprocess.DEVNULL)
    await asyncio.sleep(0.1)
    if proc.returncode not in (None, 0):
        raise ArgosError("No se pudo solicitar la apertura del workspace.")
    return outcome("He solicitado abrir el workspace.", {"path": str(path), "editor": args["editor"],
                   "argv": argv}, "workspace_dispatched")


def command_spec(project, args):
    path = path_for(project, args["cwd"])
    fd = open_directory(path)
    os.close(fd)
    try:
        argv = json.loads(args["argv_json"])
    except ValueError:
        raise ArgosError("argv_json debe ser una lista JSON de argumentos.") from None
    if (not isinstance(argv, list) or not argv or len(argv) > 50
            or any(not isinstance(a, str) or "\0" in a for a in argv) or not argv[0]):
        raise ArgosError("El comando necesita argumentos válidos.")
    executable = shutil.which(argv[0])
    if not executable:
        raise ArgosError("El ejecutable no está instalado.")
    return {"argv": [executable, *argv[1:]], "cwd": str(path),
            "scope": "Ejecuta con los permisos del usuario; puede cambiar archivos y acceder a la red."}


async def commands_exec(project, args):
    from .linux_tools import process
    from .security import safe_data
    spec = command_spec(project, args)
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "LANG", "LC_ALL", "HOME", "USER", "TMPDIR")}
    code, out, err = await process(spec["argv"], cwd=spec["cwd"], timeout=120, env=env)
    safe_data({"stdout": out, "stderr": err})
    return outcome("El comando terminó correctamente." if code == 0 else f"El comando terminó con código {code}.",
                   {**spec, "exit_code": code, "stdout": out, "stderr": err},
                   "command_passed" if code == 0 else "command_failed")


def capabilities(C):
    return [
        C("files.stat", "engineering", "Inspeccionar ruta absoluta o del proyecto y obtener SHA-256", ("path",), False, files_stat),
        C("files.list_page", "engineering", "Listar directorio paginado; offset decimal", ("path", "offset"), False, files_list),
        C("files.read_range", "engineering", "Leer UTF-8 por caracteres, hasta 32000 por página, cualquier tamaño de archivo", ("file", "offset", "limit", "expected_sha256"), False, files_read),
        C("files.patch", "engineering", "Insertar/reemplazar tramo de caracteres UTF-8 con SHA previo; permite archivos grandes", ("file", "offset", "delete_count", "content", "expected_sha256"), False, files_patch, "write"),
        C("files.mkdir", "engineering", "Crear un directorio en un padre existente", ("path",), False, files_mkdir, "write"),
        C("files.copy", "engineering", "Copiar archivo o árbol sin sobrescribir destino; SHA de files.stat", ("source", "destination", "expected_sha256"), False, files_copy, "write"),
        C("files.move", "engineering", "Mover/renombrar o restaurar desde papelera sin sobrescribir; SHA de files.stat", ("source", "destination", "expected_sha256"), False, files_move, "write"),
        C("files.delete", "engineering", "Borrar archivo o árbol trasladándolo a papelera recuperable", ("path", "expected_sha256"), False, files_delete, "write"),
        C("projects.create", "engineering", "Crear y registrar proyecto nuevo; la tarea pasa a ese proyecto", ("name", "path"), False, projects_create, "write"),
        C("workspace.open", "engineering", "Abrir workspace en code o terminal Codex (sesión externa independiente)", ("path", "editor"), False, workspace_open, "command"),
        C("commands.exec", "engineering", "Proponer argv JSON y cwd explícitos sin registro previo; siempre revisión exacta", ("cwd", "argv_json"), False, commands_exec, "command"),
    ]
