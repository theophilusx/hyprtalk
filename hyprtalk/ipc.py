from __future__ import annotations

import asyncio
import os
from asyncio import open_unix_connection
from pathlib import Path
from typing import AsyncGenerator

_HYPR_BASE = Path("/tmp/hypr")


def get_socket_dir() -> Path:
    """Return the Hyprland socket directory for the current instance."""
    sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
    if sig:
        return _HYPR_BASE / sig
    # Fallback: most recently modified instance directory
    try:
        instances = [p for p in _HYPR_BASE.iterdir() if p.is_dir()]
    except FileNotFoundError:
        raise RuntimeError("No Hyprland socket directory found at /tmp/hypr")
    if not instances:
        raise RuntimeError("No Hyprland instances found in /tmp/hypr")
    return max(instances, key=lambda p: p.stat().st_mtime)


async def query(command: str, socket_dir: Path | None = None) -> str:
    """Send a command to Hyprland's .socket.sock and return the response."""
    sd = socket_dir or get_socket_dir()
    socket_path = sd / ".socket.sock"
    reader, writer = await open_unix_connection(str(socket_path))
    try:
        writer.write(command.encode())
        await writer.drain()
        response = await reader.read(1 << 20)  # 1 MiB max
        return response.decode()
    finally:
        writer.close()
        await writer.wait_closed()


async def stream_events(
    socket_dir: Path | None = None,
) -> AsyncGenerator[tuple[str, str], None]:
    """Yield (event_name, data) from Hyprland's .socket2.sock event stream."""
    sd = socket_dir or get_socket_dir()
    socket_path = sd / ".socket2.sock"
    reader, writer = await open_unix_connection(str(socket_path))
    try:
        while True:
            line = await reader.readline()
            if not line:
                break
            text = line.decode().strip()
            if ">>" not in text:
                continue
            name, _, data = text.partition(">>")
            yield name, data
    finally:
        writer.close()
        await writer.wait_closed()
