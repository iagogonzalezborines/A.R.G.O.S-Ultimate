import asyncio
import json
import os
import uuid
from pathlib import Path

from .models import ArgosError


def state_directory():
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "argos"


async def call(directory, message):
    message = {"request_id": uuid.uuid4().hex, **message}
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_unix_connection(str(Path(directory) / "core.sock"), limit=1024 * 1024), 3)
    except (OSError, TimeoutError):
        raise ArgosError("El Core no está activo. Inícialo con «argos serve».") from None
    try:
        writer.write(json.dumps(message, ensure_ascii=False).encode() + b"\n")
        await writer.drain()
        data = await asyncio.wait_for(reader.readline(), 120)
        result = json.loads(data)
        if "error" in result:
            raise ArgosError(result["error"])
        return result
    finally:
        writer.close()
        await writer.wait_closed()
