from __future__ import annotations

import asyncio
import os
from asyncio import open_unix_connection
from pathlib import Path
from typing import AsyncGenerator

def _hypr_base() -> Path:
    """Return the Hyprland base socket directory, preferring XDG_RUNTIME_DIR."""
    xdg = os.environ.get("XDG_RUNTIME_DIR")
    if xdg:
        candidate = Path(xdg) / "hypr"
        if candidate.is_dir():
            return candidate
    return Path("/tmp/hypr")


def get_socket_dir() -> Path:
    """Return the Hyprland socket directory for the current instance."""
    base = _hypr_base()
    sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
    if sig:
        return base / sig
    # Fallback: most recently modified instance directory
    try:
        instances = [p for p in base.iterdir() if p.is_dir()]
    except FileNotFoundError:
        raise RuntimeError(f"No Hyprland socket directory found at {base}")
    if not instances:
        raise RuntimeError(f"No Hyprland instances found in {base}")
    return max(instances, key=lambda p: p.stat().st_mtime)


def _format_command(command: str) -> bytes:
    """Encode a command for Hyprland's socket protocol.

    Hyprland ≥0.45 uses the form ``[flags]/command`` where flags precede the
    slash (e.g. ``j/activewindow`` for JSON output).  Older call sites pass
    ``command -j``; translate those transparently.
    """
    cmd = command.strip()
    if cmd.endswith(" -j"):
        cmd = "j/" + cmd[:-3].rstrip()
    return cmd.encode()


async def query(command: str, socket_dir: Path | None = None) -> str:
    """Send a command to Hyprland's .socket.sock and return the response."""
    sd = socket_dir or get_socket_dir()
    socket_path = sd / ".socket.sock"
    reader, writer = await open_unix_connection(str(socket_path))
    try:
        writer.write(_format_command(command))
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
