#!/usr/bin/env python3
"""Local IPC measurements, isolated from user data and without model calls."""
import asyncio
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from argos.transport import call


async def main():
    with tempfile.TemporaryDirectory(prefix="argos-benchmark-") as tmp:
        state = Path(tmp)
        proc = await asyncio.create_subprocess_exec(
            sys.executable, str(ROOT / "argos"), "--state-dir", str(state), "serve",
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
        try:
            for _ in range(100):
                if (state / "core.sock").exists():
                    break
                await asyncio.sleep(0.02)
            results = {}
            for label, message in (
                ("greeting_ipc", {"method": "say", "text": "hola"}),
                ("status_ipc", {"method": "tasks"}),
                ("voice_meter_ipc", {"method": "voice.state"}),
            ):
                samples = []
                for _ in range(100):
                    start = time.perf_counter()
                    await call(state, message)
                    samples.append((time.perf_counter() - start) * 1000)
                results[label] = {"samples": 100, "median_ms": round(statistics.median(samples), 3),
                                  "p95_ms": round(sorted(samples)[94], 3)}
            start = time.perf_counter()
            reply = await call(state, {"method": "run", "capability": "system.info"})
            while True:
                task = (await call(state, {"method": "task", "task_id": reply["task_id"]}))["data"]
                if task["status"] not in ("QUEUED", "RUNNING"):
                    break
                await asyncio.sleep(0.001)
            results["system_info_end_to_end_ms"] = round((time.perf_counter() - start) * 1000, 3)
            results["scope"] = "Local IPC only. Excludes STT, inference, TTS and physical audio latency."
            print(json.dumps(results, indent=2))
        finally:
            proc.terminate()
            await proc.communicate()


asyncio.run(main())
