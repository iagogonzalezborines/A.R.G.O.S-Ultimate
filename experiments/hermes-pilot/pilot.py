"""Isolated launch and capability broker for the Hermes evaluation, not an agent runtime."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import secrets
import socket
import sqlite3
import struct
import subprocess
import threading
import time

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "source"
STATE = ROOT / "state/hermes"
FIXTURE = ROOT / "workspaces/disposable"
SOCKET = ROOT / "private/broker.sock"
PYTHON = ROOT / "env/bin/python"
PIN = "0073fa98cfcf61c066a919df4b336924720f8463"


def environment():
    """Allowlist environment: never inherit credentials, CODEX_HOME, proxies or agents."""
    return {
        "HOME": str(ROOT / "home"), "HERMES_HOME": str(STATE),
        "HERMES_RUNTIME_DIR": str(ROOT / "tools"),
        "HERMES_PYTHON": str(PYTHON), "CODEX_HOME": str(ROOT / "state/codex"),
        "XDG_CONFIG_HOME": str(ROOT / "home/.config"),
        "XDG_DATA_HOME": str(ROOT / "home/.local/share"),
        "XDG_CACHE_HOME": str(ROOT / "home/.cache"),
        "XDG_STATE_HOME": str(ROOT / "home/.local/state"),
        "PATH": ":".join(map(str, [ROOT / "env/bin", ROOT / "tools/node-26.12.1-linux-x64/bin",
                                    ROOT / "tools/npm-12.0.2-linux-x64/bin", ROOT / "bin", Path("/usr/bin"), Path("/bin")])),
        "LANG": "C.UTF-8", "TERM": "xterm-256color", "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": str(SOURCE), "UV_CACHE_DIR": str(ROOT / "cache"),
    }


def sandbox(argv, *, network=False, desktop=False, codex_write=False, controller_configure=False):
    """OS boundary shared by native Hermes, its tools, plugins and their children."""
    cmd = ["/usr/bin/bwrap", "--die-with-parent", "--new-session", "--unshare-all"]
    if network:
        cmd += ["--share-net"]
    for path in ("/usr", "/bin", "/sbin", "/lib", "/lib64"):
        if Path(path).exists():
            cmd += ["--ro-bind", path, path]
    cmd += ["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--dir", "/run"]
    for path in ("/etc/ssl", "/etc/ca-certificates", "/etc/resolv.conf", "/etc/hosts", "/etc/nsswitch.conf",
                 "/etc/fonts", "/etc/localtime", "/etc/ld.so.cache"):
        if Path(path).exists():
            cmd += ["--ro-bind", path, path]
    for path in (SOURCE, ROOT / "env", ROOT / "tools", ROOT / "bin", ROOT / "checks", ROOT / "pilot.py"):
        if path.exists():
            cmd += ["--ro-bind", str(path), str(path)]
    for path in (STATE, ROOT / "home", ROOT / "cache", ROOT / "state/codex"):
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        cmd += ["--bind", str(path), str(path)]
    for path in (STATE / "config.yaml", STATE / "plugins", STATE / "skills", STATE / "desktop-plugins"):
        if controller_configure and path == STATE / "config.yaml":
            continue
        if path.exists():
            cmd += ["--ro-bind", str(path), str(path)]
    cmd += ["--bind" if codex_write else "--ro-bind", str(FIXTURE), str(FIXTURE)]
    if SOCKET.exists():
        cmd += ["--ro-bind", str(SOCKET), "/run/argos-broker.sock"]
    env = environment()
    if desktop:
        runtime = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
        wayland = os.environ.get("WAYLAND_DISPLAY", "wayland-1")
        display = runtime / wayland
        if not display.is_socket():
            raise RuntimeError("No live Wayland socket")
        cmd += ["--dir", "/run/pilot", "--ro-bind", str(display), "/run/pilot/wayland-0"]
        env.update({"XDG_RUNTIME_DIR": "/run/pilot", "WAYLAND_DISPLAY": "wayland-0",
                    "XDG_SESSION_TYPE": "wayland", "XDG_CURRENT_DESKTOP": "Hyprland",
                    "ELECTRON_OZONE_PLATFORM_HINT": "wayland",
                    "HERMES_DESKTOP_HERMES_ROOT": str(SOURCE),
                    "HERMES_DESKTOP_PYTHON": str(PYTHON)})
        # GPU nodes are deliberately absent: use software rendering for this pilot.
    cmd += ["--clearenv"]
    for key, value in env.items():
        cmd += ["--setenv", key, value]
    return cmd + ["--chdir", str(FIXTURE), "--", *map(str, argv)]


class Broker:
    """No model, tasks or memory. The private ledger only records one-use capabilities."""
    def __init__(self):
        import fcntl
        self.owner = open(ROOT / "private/broker.lock", "a")
        try:
            fcntl.flock(self.owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.owner.close()
            raise
        self.lock = threading.Lock()
        self.db = sqlite3.connect(ROOT / "private/grants.sqlite", check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS grants (id TEXT PRIMARY KEY, payload TEXT, digest TEXT, approved INTEGER DEFAULT 0, used INTEGER DEFAULT 0)")
        self.db.commit()
        self.socket = socket.socket(socket.AF_UNIX)
        if SOCKET.exists():
            SOCKET.unlink()
        self.socket.bind(str(SOCKET))
        SOCKET.chmod(0o600)
        self.socket.listen(8)

    def audit(self, operation, outcome, **metadata):
        with (ROOT / "reports/broker-audit.jsonl").open("a") as f:
            f.write(json.dumps({"time": time.time(), "operation": operation, "outcome": outcome, **metadata}) + "\n")

    def directory(self, relative):
        if not isinstance(relative, str) or not relative or "\x00" in relative:
            raise ValueError("Invalid relative path")
        path = PurePosixPath(relative)
        if path.is_absolute() or any(p in ("", ".", "..") for p in relative.split("/")):
            raise PermissionError("Path outside capability")
        fd = os.open(FIXTURE, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for part in path.parts[:-1]:
                nextfd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = nextfd
            return fd, path.name
        except BaseException:
            os.close(fd)
            raise

    def read(self, relative):
        fd, name = self.directory(relative)
        try:
            filefd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
            try:
                import stat
                info = os.fstat(filefd)
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 65536:
                    raise PermissionError("Only bounded regular files with one link")
                return os.read(filefd, 65537).decode()
            finally:
                os.close(filefd)
        finally:
            os.close(fd)

    def request(self, request):
        if not isinstance(request, dict):
            raise ValueError("Object required")
        op = request.get("op")
        args = request.get("args", {})
        if op == "health" and args == {}:
            return {"ready": True}
        if op == "read":
            if set(args) != {"path"}:
                raise ValueError("Unexpected argument")
            return {"content": self.read(args["path"])}
        if op == "propose":
            if set(args) != {"path", "content"} or not isinstance(args["content"], str) or len(args["content"].encode()) > 65536:
                raise ValueError("Invalid proposal")
            fd, name = self.directory(args["path"])
            try:
                try:
                    original = hashlib.sha256(self.read(args["path"]).encode()).hexdigest()
                except FileNotFoundError:
                    original = None
            finally:
                os.close(fd)
            payload = json.dumps({**args, "previous_sha256": original}, sort_keys=True)
            ident = secrets.token_hex(16)
            digest = hashlib.sha256(payload.encode()).hexdigest()
            self.db.execute("INSERT INTO grants(id,payload,digest) VALUES (?,?,?)", (ident, payload, digest))
            self.db.commit()
            return {"proposal_id": ident, "sha256": digest, "approved": False}
        if op == "apply":
            if set(args) != {"proposal_id", "sha256"}:
                raise ValueError("Apply takes only the exact proposal id and digest")
            row = self.db.execute("SELECT payload,digest,approved,used FROM grants WHERE id=?", (args["proposal_id"],)).fetchone()
            if not row or row[1] != args["sha256"] or row[2:] != (1, 0):
                raise PermissionError("Missing, mismatched, consumed or unapproved capability")
            payload = json.loads(row[0])
            try:
                current = hashlib.sha256(self.read(payload["path"]).encode()).hexdigest()
            except FileNotFoundError:
                current = None
            if current != payload["previous_sha256"]:
                raise PermissionError("Target changed since proposal")
            fd, name = self.directory(payload["path"])
            temp = ".argos-" + secrets.token_hex(16)
            try:
                # Spend first: a crash fails closed, rather than replaying a filesystem effect.
                spent = self.db.execute("UPDATE grants SET used=1 WHERE id=? AND digest=? AND approved=1 AND used=0",
                                        (args["proposal_id"], args["sha256"]))
                if spent.rowcount != 1:
                    raise PermissionError("Capability already spent")
                self.db.commit()
                out = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
                with os.fdopen(out, "wb") as f:
                    f.write(payload["content"].encode())
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(temp, name, src_dir_fd=fd, dst_dir_fd=fd)
                os.fsync(fd)
            finally:
                os.close(fd)
            return {"applied": True, "sha256": hashlib.sha256(payload["content"].encode()).hexdigest()}
        raise PermissionError("Operation not granted")

    def grant(self, ident, digest):
        """Controller-only: never exposed as an agent socket operation."""
        with self.lock:
            cur = self.db.execute("UPDATE grants SET approved=1 WHERE id=? AND digest=? AND used=0", (ident, digest))
            self.db.commit()
            if cur.rowcount != 1:
                raise ValueError("Unknown or consumed proposal")
            self.audit("controller.grant", "approved", proposal_id=ident)

    def serve(self):
        while True:
            try:
                conn, _ = self.socket.accept()
            except OSError:
                return
            with conn, self.lock:
                conn.settimeout(3)
                try:
                    _, uid, _ = struct.unpack("3i", conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                    if uid != os.getuid():
                        raise PermissionError("Wrong peer")
                    data = bytearray()
                    while b"\n" not in data:
                        chunk = conn.recv(4096)
                        if not chunk:
                            raise ValueError("Incomplete request")
                        data.extend(chunk)
                        if len(data) > 131072:
                            raise ValueError("Request too large")
                    request = json.loads(data.split(b"\n", 1)[0])
                    result = self.request(request)
                    self.audit(request.get("op"), "allowed")
                except Exception as exc:
                    result = {"error": type(exc).__name__, "message": str(exc)}
                    self.audit("request", "denied", reason=type(exc).__name__)
                try:
                    conn.sendall(json.dumps(result).encode() + b"\n")
                except (BrokenPipeError, ConnectionResetError):
                    self.audit("client.disconnect", "no_effect")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["run", "broker"])
    parser.add_argument("args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.command == "broker":
        Broker().serve()
    else:
        cmd = args.args[1:] if args.args[:1] == ["--"] else args.args
        if not cmd:
            cmd = [str(PYTHON), "-m", "tui_gateway.entry"]
        raise SystemExit(subprocess.call(sandbox(cmd)))


if __name__ == "__main__":
    main()
