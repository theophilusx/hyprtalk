from __future__ import annotations

import json
import logging
import os
import signal
from pathlib import Path

from hyprtalk.config import Config, DND_FILE, PID_FILE
from hyprtalk.events import format_window
from hyprtalk.ipc import query as ipc_query
from hyprtalk.speech import Speaker

log = logging.getLogger(__name__)


async def run_query(
    command: str,
    config: Config,
    speaker: Speaker,
    socket_dir: Path | None = None,
) -> None:
    """Dispatch a --query command: fetch state, speak result, return."""
    if command == "focus":
        resp = await ipc_query("activewindow -j", socket_dir)
        try:
            data = json.loads(resp)
        except json.JSONDecodeError:
            data = {}
        cls = data.get("class", "")
        title = data.get("title", "")
        text = format_window(cls, title, config) if cls else ""
        speaker.say(text or "No focused window", priority="high")

    elif command == "workspace":
        resp = await ipc_query("activeworkspace -j", socket_dir)
        try:
            data = json.loads(resp)
            name = data["name"]
        except (json.JSONDecodeError, KeyError):
            log.warning("workspace: unexpected IPC response: %s", resp)
            speaker.say("Workspace unavailable", priority="high")
            return
        speaker.say(f"Workspace {name}", priority="high")

    elif command == "windows":
        resp = await ipc_query("clients -j", socket_dir)
        clients = json.loads(resp)
        if not clients:
            speaker.say("No windows open", priority="normal")
            return
        by_ws: dict[str, list[str]] = {}
        for c in clients:
            ws = str(c.get("workspace", {}).get("name", "?"))
            cls = c.get("class", "unknown")
            by_ws.setdefault(ws, []).append(cls)
        parts = [
            f"Workspace {ws}: {', '.join(wins)}"
            for ws, wins in sorted(by_ws.items())
        ]
        speaker.say(". ".join(parts), priority="normal")

    elif command == "workspaces":
        resp = await ipc_query("workspaces -j", socket_dir)
        try:
            wss = json.loads(resp)
        except json.JSONDecodeError:
            log.warning("workspaces: unexpected IPC response: %s", resp)
            speaker.say("Workspaces unavailable", priority="normal")
            return
        if not wss:
            speaker.say("No workspaces", priority="normal")
            return
        parts = [
            f"Workspace {ws['name']}, {ws['windows']} window{'s' if ws['windows'] != 1 else ''}"
            for ws in sorted(wss, key=lambda w: str(w["name"]))
        ]
        speaker.say(". ".join(parts), priority="normal")

    elif command == "dnd":
        state = "on" if speaker.dnd else "off"
        speaker.say(f"Do not disturb is {state}", priority="high", bypass_dnd=True)

    elif command in ("dnd-toggle", "dnd-on", "dnd-off"):
        if command == "dnd-toggle":
            new_state = not speaker.dnd
        elif command == "dnd-on":
            new_state = True
        else:
            new_state = False
        speaker.dnd = new_state
        DND_FILE.parent.mkdir(parents=True, exist_ok=True)
        DND_FILE.write_text("on" if new_state else "off")
        _signal_daemon()
        state_str = "on" if new_state else "off"
        speaker.say(f"Do not disturb {state_str}", priority="high", bypass_dnd=True)

    else:
        log.error("Unknown query command: %s", command)


def _signal_daemon() -> None:
    """Send SIGUSR1 to the daemon if it is running (PID file exists)."""
    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, signal.SIGUSR1)
    except (FileNotFoundError, ValueError, ProcessLookupError):
        pass  # Daemon not running — state file already written, will be read at next start
