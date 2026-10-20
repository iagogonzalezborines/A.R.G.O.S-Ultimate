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

    def snapshot(self):
        return {"level": round(self.level, 4), "state": self.state, "generation": self.generation}

    async def _stop(self):
        if self.job:
            self.job.cancel()
            await asyncio.gather(self.job, return_exceptions=True)
            self.job = None
        # A task cancelled before its coroutine starts never enters its finally
        # block. The output owner must still reap the newly spawned player.
        if self.process and self.process.returncode is None:
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
                player, str(path), stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL)
            self.state = "speaking"
            self.job = asyncio.create_task(self._meter(levels, chunk / rate))

    async def play_stream(self, chunks, first_audio=None):
        """Play mono 24 kHz s16 PCM as it arrives, with bounded buffering."""
        player = shutil.which("pw-play") or shutil.which("aplay")
        if not player:
            raise ArgosError("No se ha encontrado un reproductor PCM.")
        async with self.lock:
            await self._stop()
            self.generation += 1
            self.last_error = None
            self.state = "thinking"
            self.job = asyncio.create_task(self._stream(chunks, player, first_audio))

    async def _stream(self, chunks, player, first_audio):
        proc = None
        deadline = time.monotonic()
        first = True
        try:
            async with contextlib.aclosing(chunks):
                async for data in chunks:
                    if not proc:
                        args = (["--raw", "--rate=24000", "--channels=1", "--format=s16",
                                 "--latency=80ms", "-"] if Path(player).name != "aplay"
                                else ["-t", "raw", "-r", "24000", "-c", "1", "-f", "S16_LE", "-"])
                        proc = self.process = await asyncio.create_subprocess_exec(
                            player, *args, stdin=asyncio.subprocess.PIPE,
                            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
                    # Feed and meter at 20 ms intervals. The subprocess pipe and
                    # worker reader are bounded; a long answer cannot grow a PCM queue.
                    for offset in range(0, len(data), 960):
                        frame = data[offset:offset + 960]
                        proc.stdin.write(frame)
                        await proc.stdin.drain()
                        self.level, self.state = rms16(frame), "speaking"
                        if first:
                            first = False
                            if first_audio:
                                first_audio()
                        deadline = max(deadline + len(frame) / 48000, time.monotonic())
                        await asyncio.sleep(max(0, deadline - time.monotonic()))
                if proc:
                    proc.stdin.close()
                    await asyncio.wait_for(proc.wait(), 5)
                    if proc.returncode:
                        raise ArgosError("El reproductor no pudo enviar audio a la salida seleccionada.")
        except (ArgosError, OSError, ValueError, TimeoutError) as error:
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
