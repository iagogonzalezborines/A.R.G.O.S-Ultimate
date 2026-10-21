import asyncio
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from argos.providers import OllamaInterpreter
from argos.transport import call


ROOT = Path(__file__).resolve().parents[1]


class HTTPProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_http_contract_and_schema(self):
        requests = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                decision = {"kind": "capability", "speech": "", "agent": "computer",
                            "capability": "system.info", "arguments": {}}
                body = json.dumps({"done": True, "message": {"content": json.dumps(decision)}}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            provider = OllamaInterpreter("test-model", f"http://127.0.0.1:{server.server_port}")
            decision = await provider.decide("consulta la máquina", {"project": None})
            self.assertEqual(decision.capability, "system.info")
            self.assertEqual(len(requests), 1)
            self.assertFalse(requests[0]["stream"])
            self.assertIn("ARGOS interaction contract", requests[0]["messages"][0]["content"])
            self.assertEqual(requests[0]["format"]["type"], "object")
        finally:
            await asyncio.to_thread(server.shutdown)
            server.server_close()
            thread.join()


class DaemonTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name) / "state"
        self.proc = await asyncio.create_subprocess_exec(
            sys.executable, str(ROOT / "argos"), "--state-dir", str(self.state), "serve",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        for _ in range(100):
            if (self.state / "core.sock").exists():
                break
            if self.proc.returncode is not None:
                raise AssertionError((await self.proc.stderr.read()).decode())
            await asyncio.sleep(0.02)
        else:
            raise AssertionError("Core did not start")

    async def asyncTearDown(self):
        if self.proc.returncode is None:
            self.proc.terminate()
        stdout, stderr = await asyncio.wait_for(self.proc.communicate(), 3)
        self.assertEqual(stdout, b"")
        self.assertEqual(stderr, b"")
        self.tmp.cleanup()

    async def test_clients_disconnect_but_task_and_core_survive(self):
        response = await call(self.state, {"method": "run", "capability": "system.info"})
        task_id = response["task_id"]
        for _ in range(100):
            task = (await call(self.state, {"method": "task", "task_id": task_id}))["data"]
            if task["status"] == "COMPLETED":
                break
            await asyncio.sleep(0.01)
        self.assertEqual(task["status"], "COMPLETED")
        self.assertEqual((self.state / "core.sock").stat().st_mode & 0o777, 0o600)
        self.assertIsNone(self.proc.returncode)

    async def test_duplicate_core_does_not_touch_running_socket(self):
        proc = await asyncio.create_subprocess_exec(
            sys.executable, str(ROOT / "argos"), "--state-dir", str(self.state), "serve",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await asyncio.wait_for(proc.communicate(), 3)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("Ya hay un Core activo", stderr.decode())
        self.assertEqual((await call(self.state, {"method": "say", "text": "hola"}))["speech"], "Hola.")

    async def test_malformed_client_does_not_crash_core(self):
        reader, writer = await asyncio.open_unix_connection(str(self.state / "core.sock"))
        writer.write(b"not-json\n")
        await writer.drain()
        self.assertIn("error", json.loads(await reader.readline()))
        writer.close()
        await writer.wait_closed()
        self.assertEqual((await call(self.state, {"method": "say", "text": "hola"}))["speech"], "Hola.")

    async def test_cli_end_to_end(self):
        proc = await asyncio.create_subprocess_exec(
            sys.executable, str(ROOT / "argos"), "--state-dir", str(self.state),
            "--json", "run", "system.info", "--wait",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await asyncio.wait_for(proc.communicate(), 3)
        self.assertEqual(proc.returncode, 0, stderr.decode())
        self.assertEqual(json.loads(stdout)["data"]["status"], "COMPLETED")

    async def test_inventory_cli_queries_daemon_without_enqueuing_work(self):
        proc = await asyncio.create_subprocess_exec(
            sys.executable, str(ROOT / "argos"), "--state-dir", str(self.state),
            "--json", "system-status", "--refresh",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await asyncio.wait_for(proc.communicate(), 5)
        self.assertEqual(proc.returncode, 0, stderr.decode())
        report = json.loads(stdout)["data"]
        self.assertEqual(report["environment"]["status"], "observed")
        self.assertFalse(report["environment"]["stale"])
        self.assertTrue(all("status" in cap and "reason" in cap for cap in report["capabilities"]))
        self.assertEqual((await call(self.state, {"method": "tasks"}))["data"], [])

    async def test_console_draws_and_restores_terminal_without_stopping_core(self):
        import pty
        import signal
        master, slave = pty.openpty()
        console = await asyncio.create_subprocess_exec(
            sys.executable, str(ROOT / "argos"), "--state-dir", str(self.state), "console",
            stdin=slave, stdout=slave, stderr=slave)
        os.close(slave)
        try:
            await asyncio.sleep(0.2)
            console.send_signal(signal.SIGINT)
            await asyncio.wait_for(console.wait(), 3)
            os.set_blocking(master, False)
            chunks = []
            while True:
                try:
                    chunk = os.read(master, 65536)
                    if not chunk:
                        break
                    chunks.append(chunk)
                except OSError:
                    break
            output = b"".join(chunks)
            self.assertIn(b"\x1b[?1049h", output)
            self.assertIn(b"\x1b[?1049l", output)
            self.assertNotIn(b"Traceback", output)
            self.assertIsNone(self.proc.returncode)
            self.assertEqual((await call(self.state, {"method": "say", "text": "hola"}))["speech"], "Hola.")
        finally:
            if console.returncode is None:
                console.kill()
                await console.wait()
            os.close(master)

    async def test_monitor_switches_views_resizes_and_closes_without_stopping_core(self):
        import pty
        import termios
        master, slave = pty.openpty()
        termios.tcsetwinsize(slave, (32, 100))
        panel = await asyncio.create_subprocess_exec(
            sys.executable, str(ROOT / "argos"), "--state-dir", str(self.state), "monitor", "tasks",
            stdin=slave, stdout=slave, stderr=slave, env={**os.environ, "TERM": "xterm-256color"})
        os.close(slave)
        os.set_blocking(master, False)
        output = bytearray()
        def drain():
            while True:
                try:
                    chunk = os.read(master, 65536)
                    if not chunk:
                        break
                    output.extend(chunk)
                except OSError:
                    break
        try:
            for key in (b"", b"t", b"c", b"t"):
                if key:
                    os.write(master, key)
                for _ in range(5):
                    await asyncio.sleep(.04)
                    drain()
            termios.tcsetwinsize(master, (24, 80))
            await asyncio.sleep(.15)
            drain()
            os.write(master, b"q")
            await asyncio.wait_for(panel.wait(), 3)
            drain()
            self.assertEqual(panel.returncode, 0, output.decode(errors="replace"))
            self.assertIn(b"TAREAS", output)
            self.assertIn(b"CONVERSACIONES", output)
            self.assertNotIn(b"Traceback", output)
            self.assertEqual((await call(self.state, {"method": "say", "text": "hola"}))["speech"], "Hola.")
        finally:
            if panel.returncode is None:
                panel.kill()
                await panel.wait()
            os.close(master)
