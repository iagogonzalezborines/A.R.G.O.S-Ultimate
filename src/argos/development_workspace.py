"""Linux adapter for private candidates and explicitly planned, isolated checks."""
import asyncio
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import stat

from .filesystem import open_file, path_for
from .models import ArgosError
from .security import public_text


EXCLUDED = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache",
            ".mypy_cache", ".argos-trash", "dist", "build"}
MAX_BYTES = 128 * 1024 * 1024
MAX_FILES = 10000


def tree(root):
    """Bounded manifest; no links, private paths, devices or dependency caches."""
    result, total = {}, 0
    for directory, dirs, files in os.walk(root, followlinks=False):
        def allowed(name):
            path = Path(directory) / name
            try:
                path_for(None, str(path))
                return name not in EXCLUDED and not path.is_symlink()
            except ArgosError:
                return False
        dirs[:] = sorted(d for d in dirs if allowed(d))
        for name in sorted(files):
            if not allowed(name):
                continue
            path = Path(directory) / name
            if not stat.S_ISREG(path.lstat().st_mode):
                continue
            with open_file(path) as file:
                data = file.read(MAX_BYTES - total + 1)
            total += len(data)
            if total > MAX_BYTES or len(result) >= MAX_FILES:
                raise ArgosError("La copia de desarrollo excede 128 MiB o 10000 archivos; concreta el proyecto.")
            result[str(path.relative_to(root))] = {
                "sha256": hashlib.sha256(data).hexdigest(), "mode": stat.S_IMODE(path.stat().st_mode)}
    return result


def digest(manifest):
    return hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()


class LinuxDevelopmentWorkspace:
    def __init__(self, directory, source_root):
        self.directory = Path(directory) / "development"
        self.source_root = Path(source_root).resolve()

    def identity(self):
        from . import __version__
        return {"name": "ARGOS", "version": __version__, "source_root": str(self.source_root),
                "self_development": (self.source_root / "src/argos/core.py").is_file(),
                "activation_available": False,
                "checks": "bubblewrap; no network, audio, desktop, host home or installed credentials",
                "sandbox_installed": bool(shutil.which("bwrap"))}

    def prepare(self, task_id, source):
        root = self.directory / task_id
        if root.exists():
            raise ArgosError("Ya existe una copia para esta tarea; no se sobrescribe ni repite su preparación.")
        source = path_for(None, source) if source else None
        if source and (not source.is_dir() or source.is_symlink() or source == Path.home()
                       or source == Path(source.anchor) or self.directory.is_relative_to(source)):
            raise ArgosError("Selecciona una carpeta de código concreta, ajena al estado de ARGOS.")
        manifest = tree(source) if source else {}
        root.mkdir(parents=True, mode=0o700)
        baseline, workspace = root / "baseline", root / "workspace"
        baseline.mkdir(mode=0o700)
        workspace.mkdir(mode=0o700)
        for name, info in manifest.items():
            with open_file(source / name) as file:
                data = file.read(MAX_BYTES + 1)
            if hashlib.sha256(data).hexdigest() != info["sha256"]:
                raise ArgosError("El origen cambió durante la copia; crea una tarea nueva.")
            for destination in (baseline / name, workspace / name):
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
                destination.chmod(info["mode"] & 0o777)
        (root / "baseline.json").write_text(json.dumps(manifest, sort_keys=True))
        return {"source": str(source) if source else None, "workspace": str(workspace),
                "base_sha256": digest(manifest), "copied_files": len(manifest),
                "excluded": sorted(EXCLUDED) + ["credential paths", "symlinks", "special files"]}

    def scope(self, state, name, args):
        root = Path(state["workspace"])
        if name.startswith("files."):
            for key in ("path", "file", "source", "destination"):
                if key not in args:
                    continue
                path = path_for({"root": str(root)}, args[key])
                if not path.is_relative_to(root) or not path.resolve().is_relative_to(root.resolve()):
                    raise ArgosError("La autorización de desarrollo solo cubre su copia de trabajo.")
                if any(part in EXCLUDED - {".argos-trash"} for part in path.relative_to(root).parts):
                    raise ArgosError("Esa carpeta está excluida del desarrollo delegado.")
                if path == root and name in ("files.delete", "files.move", "files.copy"):
                    raise ArgosError("No se puede sustituir la raíz de la copia de trabajo.")

    def review(self, state):
        root = Path(state["workspace"]).parent
        before = json.loads((root / "baseline.json").read_text())
        after = tree(root / "workspace")
        changed = [name for name in sorted(before.keys() | after.keys()) if before.get(name) != after.get(name)]
        # The patch is an artifact, not prompt/log content. Large/binary changes
        # remain reviewable in the candidate and the hash manifest.
        patch = []
        for name in changed:
            old, new = root / "baseline" / name, root / "workspace" / name
            try:
                if any(p.exists() and p.stat().st_size > 256000 for p in (old, new)):
                    continue
                a = old.read_text() if old.exists() else ""
                b = new.read_text() if new.exists() else ""
                patch.extend(difflib.unified_diff(a.splitlines(True), b.splitlines(True),
                                                fromfile="a/" + name, tofile="b/" + name))
            except UnicodeError:
                continue
        (root / "changes.patch").write_text("".join(patch))
        (root / "candidate.json").write_text(json.dumps(after, sort_keys=True))
        return {"candidate": str(root / "workspace"), "patch": str(root / "changes.patch"),
                "manifest": str(root / "candidate.json"), "candidate_sha256": digest(after),
                "changed_files": changed[:200], "changed_count": len(changed), "activated": False}

    def sandbox_argv(self, workspace, argv):
        binary = shutil.which("bwrap")
        if not binary:
            raise ArgosError("Falta bubblewrap para ejecutar pruebas aisladas; no se ejecutarán en el anfitrión.")
        command = [binary, "--unshare-all", "--die-with-parent", "--new-session", "--cap-drop", "ALL",
                   "--clearenv"]
        # Mount only system runtimes, never /, /home, /run, /etc or the real /dev.
        for path in ("/usr", "/bin", "/sbin", "/lib", "/lib64"):
            if Path(path).exists():
                command += ["--ro-bind", path, path]
        command += ["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--dir", "/home/argos",
                    "--bind", str(workspace), "/workspace", "--chdir", "/workspace",
                    "--setenv", "PATH", "/usr/local/bin:/usr/bin:/bin", "--setenv", "HOME", "/home/argos",
                    "--setenv", "LANG", "C.UTF-8", "--setenv", "PYTHONPATH", "/workspace/src",
                    "--setenv", "PYTHONDONTWRITEBYTECODE", "1", "--", *argv]
        return command

    async def check(self, state, argv):
        command = self.sandbox_argv(state["workspace"], argv)
        proc = await asyncio.create_subprocess_exec(*command, stdout=asyncio.subprocess.PIPE,
                                                    stderr=asyncio.subprocess.STDOUT, start_new_session=True)
        data = bytearray()
        async def read():
            while chunk := await proc.stdout.read(8192):
                data.extend(chunk)
                if len(data) > 64000:
                    raise ArgosError("La prueba excedió el límite de salida de 64 KB.")
            await proc.wait()
        try:
            await asyncio.wait_for(read(), 120)
        finally:
            # Kill the entire namespace/process group on cancellation/timeout
            # too; no test process may outlive its task.
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await proc.wait()
        output = data.decode(errors="replace")
        try:
            public_text(output, 64000)
        except ArgosError:
            output = "Salida omitida: contiene datos protegidos o caracteres de control."
        return {"argv": argv, "exit_code": proc.returncode, "output": output,
                "verification": "command_passed" if proc.returncode == 0 else "command_failed",
                "isolation": "bubblewrap", "network": False}
