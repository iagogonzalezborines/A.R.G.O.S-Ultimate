"""Single PCM playback owner and output meter, shared by TTS and WAV playback."""
import asyncio
import contextlib
import math
import shutil
import struct
import time
import wave
from pathlib import Path

from .models import ArgosError


STREAM_TAIL = b"\0" * 9600  # 200 ms of mono 24 kHz s16 after the final TTS sample.


def rms16(data):
    count = len(data) // 2
    if not count:
        return 0.0
    samples = struct.unpack("<" + "h" * count, data[:count * 2])
    return min(1.0, math.sqrt(sum(x * x for x in samples) / count) / 32768.0)


class VoiceOutput:
    def __init__(self):
        self.level, self.state = 0.0, "idle"
        self.job, self.process = None, None
        self.generation = 0
        self.lock = asyncio.Lock()
        self.last_error = None
        self.target = None
        self.last_stream = {}

    def snapshot(self):
        return {"level": round(self.level, 4), "state": self.state, "generation": self.generation,
                "last_stream": dict(self.last_stream)}

    async def _stop(self):
        # Silence the device before closing the generator: cancelling local TTS
        # may take seconds while its worker is reaped.
        if self.process and self.process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                self.process.terminate()
        if self.job:
            self.job.cancel()
            await asyncio.gather(self.job, return_exceptions=True)
            self.job = None
        if self.last_stream.get("status") in ("preparing", "sending"):
            self.last_stream["status"] = "interrupted"
        # A task cancelled before its coroutine starts never enters its finally
        # block. The output owner must still reap the newly spawned player.
        if self.process and self.process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), 2)
            except TimeoutError:
                self.process.kill()
                await self.process.wait()
        self.process = None
        self.level, self.state = 0.0, "idle"

    async def stop(self):
        async with self.lock:
            await self._stop()

    async def play(self, filename):
        path = Path(filename).expanduser().resolve(strict=True)
        if path.stat().st_size > 32 * 1024 * 1024:
            raise ArgosError("El audio excede 32 MiB.")
        player = shutil.which("pw-play") or shutil.which("aplay")
        if not player:
            raise ArgosError("No se ha encontrado un reproductor PCM.")
        if self.target and Path(player).name == "aplay":
            raise ArgosError("La cancelación de eco requiere pw-play.")
        try:
            with wave.open(str(path), "rb") as wav:
                if wav.getsampwidth() != 2 or wav.getcomptype() != "NONE" or wav.getnchannels() > 2:
                    raise ArgosError("Usa un WAV PCM de 16 bits, mono o estéreo.")
                rate = wav.getframerate()
                if not 8000 <= rate <= 192000:
                    raise ArgosError("Frecuencia de audio no admitida.")
                chunk = max(1, rate // 20)
                levels = []
                while data := wav.readframes(chunk):
                    levels.append(rms16(data))
        except (wave.Error, EOFError):
            raise ArgosError("El archivo no es un WAV PCM válido.") from None
        async with self.lock:
            await self._stop()
            self.generation += 1
            self.last_error = None
            self.process = await asyncio.create_subprocess_exec(
                player, *(["--target", self.target] if self.target else []), str(path), stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL)
            self.state = "speaking"
            self.job = asyncio.create_task(self._meter(levels, chunk / rate))

    async def play_stream(self, chunks, first_audio=None):
        """Play mono 24 kHz s16 PCM as it arrives, with bounded buffering."""
        player = shutil.which("pw-play") or shutil.which("aplay")
        if not player:
            raise ArgosError("No se ha encontrado un reproductor PCM.")
        if self.target and Path(player).name == "aplay":
            raise ArgosError("La cancelación de eco requiere pw-play.")
        async with self.lock:
            await self._stop()
            self.generation += 1
            self.last_error = None
            self.state = "thinking"
            self.last_stream = {"status": "preparing", "generated_bytes": 0,
                                "sent_bytes": 0, "padding_bytes": 0, "source_complete": False,
                                "player_exit_code": None}
            self.job = asyncio.create_task(self._stream(chunks, player, first_audio))

    async def _stream(self, chunks, player, first_audio):
        proc = None
        deadline = time.monotonic()
        first = True

        async def feed(data, padding=False):
            nonlocal proc, deadline, first
            if not proc:
                args = (["--raw", "--rate=24000", "--channels=1", "--format=s16",
                         "--latency=80ms", "-"] if Path(player).name != "aplay"
                        else ["-t", "raw", "-r", "24000", "-c", "1", "-f", "S16_LE", "-"])
                if self.target:
                    args = ["--target", self.target, *args]
                proc = self.process = await asyncio.create_subprocess_exec(
                    player, *args, stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
                deadline = time.monotonic()
            # Feed and meter at 20 ms intervals, without accumulating clock drift.
            for offset in range(0, len(data), 960):
                frame = data[offset:offset + 960]
                proc.stdin.write(frame)
                await proc.stdin.drain()
                self.last_stream["sent_bytes"] += len(frame)
                if padding:
                    self.last_stream["padding_bytes"] += len(frame)
                self.last_stream["status"] = "sending"
                self.level, self.state = rms16(frame), "speaking"
                if first:
                    first = False
                    if first_audio:
                        first_audio()
                deadline = max(deadline + len(frame) / 48000, time.monotonic())
                await asyncio.sleep(max(0, deadline - time.monotonic()))

        try:
            pending = bytearray()
            async with contextlib.aclosing(chunks):
                async for data in chunks:
                    self.last_stream["generated_bytes"] += len(data)
                    # Collect 240 ms of PCM before opening the player. Starting
                    # at the very first 80 ms chunk exposes cold-generation stalls.
                    if not proc:
                        pending.extend(data)
                        if len(pending) < 11520:
                            continue
                        data = bytes(pending)
                        pending.clear()
                    await feed(data)
                self.last_stream["source_complete"] = True
                # Very short utterances must still be played in full at EOF.
                if pending:
                    await feed(bytes(pending))
                if proc:
                    # Keep the stream alive briefly after the last phoneme so
                    # downstream resampling/AEC can flush before player EOF.
                    # Preserve every generated byte; never fade or trim speech.
                    await feed(STREAM_TAIL, padding=True)
                    proc.stdin.close()
                    await asyncio.wait_for(proc.wait(), 5)
                    self.last_stream["player_exit_code"] = proc.returncode
                    if proc.returncode:
                        raise ArgosError("El reproductor no pudo enviar audio a la salida seleccionada.")
                self.last_stream["status"] = "completed" if proc else "empty"
        except asyncio.CancelledError:
            self.last_stream["status"] = "interrupted"
            raise
        except (ArgosError, OSError, ValueError, TimeoutError) as error:
            self.last_stream["status"] = "failed"
            self.last_error = (str(error) if isinstance(error, ArgosError)
                               else "No se pudo completar la reproducción de voz.")
            raise ArgosError(self.last_error) from None
        finally:
            if proc and proc.returncode is None:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), 2)
                except TimeoutError:
                    proc.kill()
                    await proc.wait()
            self.level, self.state = 0.0, "error" if self.last_error else "idle"

    async def _meter(self, levels, interval):
        proc = self.process
        start = time.monotonic()
        try:
            for index, level in enumerate(levels):
                if proc.returncode is not None:
                    break
                self.level = level
                await asyncio.sleep(max(0, start + (index + 1) * interval - time.monotonic()))
            await asyncio.wait_for(proc.wait(), 5)
            if proc.returncode:
                raise ArgosError("El reproductor no pudo enviar audio a la salida seleccionada.")
        except (ArgosError, OSError, TimeoutError) as error:
            self.last_error = str(error)
            raise
        finally:
            if proc.returncode is None:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), 2)
                except TimeoutError:
                    proc.kill()
                    await proc.wait()
            self.level, self.state = 0.0, "error" if self.last_error else "idle"
