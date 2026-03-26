from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from hyprtalk.config import Config
from hyprtalk.ipc import query, stream_events
from hyprtalk.speech import Speaker

log = logging.getLogger(__name__)


@dataclass
class WindowInfo:
    address: str
    cls: str       # "class" is a Python keyword
    title: str
    workspace: str


class WindowCache:
    """In-memory map of address → WindowInfo, kept current by open/close/move events."""

    def __init__(self) -> None:
        self._windows: dict[str, WindowInfo] = {}

    def update_from_clients(self, clients_json: str) -> None:
        clients = json.loads(clients_json)
        for c in clients:
            addr = c["address"]
            self._windows[addr] = WindowInfo(
                address=addr,
                cls=c.get("class", ""),
                title=c.get("title", ""),
                workspace=str(c.get("workspace", {}).get("name", "")),
            )

    def add(self, info: WindowInfo) -> None:
        self._windows[info.address] = info

    def remove(self, address: str) -> WindowInfo | None:
        return self._windows.pop(address, None)

    def move(self, address: str, new_workspace: str) -> None:
        if address in self._windows:
            self._windows[address].workspace = new_workspace

    def get(self, address: str) -> WindowInfo | None:
        return self._windows.get(address)

    def all_windows(self) -> list[WindowInfo]:
        return list(self._windows.values())


def format_window(cls: str, title: str, config: Config) -> str:
    """Format a window identifier for speech per config settings."""
    parts = []
    if config.window_announce_class and cls:
        parts.append(cls)
    if config.window_announce_title and title:
        t = title
        if config.window_max_title_length > 0:
            t = t[: config.window_max_title_length]
        parts.append(t)
    return ", ".join(parts)


# --- Individual event handlers ---

def _on_activewindow(
    data: str, config: Config, speaker: Speaker, cache: WindowCache, show_monitor: bool
) -> None:
    ec = config.events.get("focus")
    if not ec or not ec.enabled:
        return
    cls, _, title = data.partition(",")
    text = format_window(cls.strip(), title.strip(), config)
    if text:
        speaker.say(text, priority=ec.priority)


def _on_openwindow(
    data: str, config: Config, speaker: Speaker, cache: WindowCache, show_monitor: bool
) -> None:
    ec = config.events.get("open_window")
    if not ec or not ec.enabled:
        return
    parts = data.split(",", 3)
    if len(parts) < 3:
        return
    address = parts[0]
    workspace = parts[1]
    cls = parts[2]
    title = parts[3] if len(parts) > 3 else ""
    cache.add(WindowInfo(address=address, cls=cls, title=title, workspace=workspace))
    window_name = format_window(cls, title, config) or cls
    speaker.say(f"{window_name} opened on workspace {workspace}", priority=ec.priority)


def _on_closewindow(
    data: str, config: Config, speaker: Speaker, cache: WindowCache, show_monitor: bool
) -> None:
    ec = config.events.get("close_window")
    if not ec or not ec.enabled:
        return
    address = data.strip()
    info = cache.remove(address)
    cls = info.cls if info else "window"
    window_name = format_window(cls, info.title if info else "", config) or cls
    speaker.say(f"{window_name} closed", priority=ec.priority)


def _on_workspace(
    data: str, config: Config, speaker: Speaker, cache: WindowCache, show_monitor: bool
) -> None:
    ec = config.events.get("workspace")
    if not ec or not ec.enabled:
        return
    name = data.strip()
    speaker.say(f"Workspace {name}", priority=ec.priority)


def _on_focusedmon(
    data: str, config: Config, speaker: Speaker, cache: WindowCache, show_monitor: bool
) -> None:
    ec = config.events.get("focused_monitor")
    if not ec or not ec.enabled:
        return
    monitor, _, workspace = data.partition(",")
    speaker.say(f"Monitor {monitor.strip()}, workspace {workspace.strip()}", priority=ec.priority)


def _on_movewindow(
    data: str, config: Config, speaker: Speaker, cache: WindowCache, show_monitor: bool
) -> None:
    ec = config.events.get("move_window")
    if not ec or not ec.enabled:
        return
    address, _, workspace = data.partition(",")
    address = address.strip()
    workspace = workspace.strip()
    cache.move(address, workspace)
    info = cache.get(address)
    cls = info.cls if info else "window"
    window_name = format_window(cls, info.title if info else "", config) or cls
    speaker.say(f"{window_name} moved to workspace {workspace}", priority=ec.priority)


def _on_fullscreen(
    data: str, config: Config, speaker: Speaker, cache: WindowCache, show_monitor: bool
) -> None:
    ec = config.events.get("fullscreen")
    if not ec or not ec.enabled:
        return
    state = "on" if data.strip() == "1" else "off"
    speaker.say(f"Fullscreen {state}", priority=ec.priority)


def _on_urgent(
    data: str, config: Config, speaker: Speaker, cache: WindowCache, show_monitor: bool
) -> None:
    ec = config.events.get("urgent")
    if not ec or not ec.enabled:
        return
    address = data.strip()
    info = cache.get(address)
    cls = info.cls if info else "window"
    window_name = format_window(cls, info.title if info else "", config) or cls
    speaker.say(f"{window_name} needs attention", priority=ec.priority)


_HANDLERS = {
    "activewindow": _on_activewindow,
    "openwindow":   _on_openwindow,
    "closewindow":  _on_closewindow,
    "workspace":    _on_workspace,
    "focusedmon":   _on_focusedmon,
    "movewindow":   _on_movewindow,
    "fullscreen":   _on_fullscreen,
    "urgent":       _on_urgent,
}

# Note: the `show_monitor` parameter is passed to every handler and is ready
# for future use. The initial implementation does not yet include monitor name
# in workspace/focus announcements, because those events don't carry monitor
# data. The `focusedmon` event (when enabled) is the primary way monitor
# context is announced. Including monitor info in other events would require
# tracking additional state and is left for a future iteration.


async def run_event_loop(
    config_holder: list,
    speaker: Speaker,
    socket_dir: Path | None = None,
    show_monitor: bool = False,
) -> None:
    """Stream Hyprland events and announce them via speaker.

    config_holder is a single-element list so that the SIGHUP handler in
    _run_daemon can update config_holder[0] and have the change visible here
    on the next event iteration.
    """
    cache = WindowCache()
    clients_json = await query("clients -j", socket_dir)
    cache.update_from_clients(clients_json)

    async for event_name, data in stream_events(socket_dir):
        handler = _HANDLERS.get(event_name)
        if handler is None:
            continue
        try:
            handler(data, config_holder[0], speaker, cache, show_monitor)
        except Exception as e:
            log.warning("Error handling event %s: %s", event_name, e)
