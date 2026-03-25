from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_PATH = Path.home() / ".config" / "hyprtalk" / "config.toml"
DATA_DIR = Path.home() / ".local" / "share" / "hyprtalk"
PID_FILE = DATA_DIR / "hyprtalk.pid"
DND_FILE = DATA_DIR / "dnd"

_DEFAULT_EVENTS: dict[str, dict] = {
    "focus":          {"enabled": True,  "priority": "high"},
    "open_window":    {"enabled": True,  "priority": "normal"},
    "close_window":   {"enabled": True,  "priority": "normal"},
    "workspace":      {"enabled": True,  "priority": "high"},
    "move_window":    {"enabled": False, "priority": "low"},
    "fullscreen":     {"enabled": True,  "priority": "normal"},
    "urgent":         {"enabled": True,  "priority": "critical"},
    "focused_monitor":{"enabled": False, "priority": "low"},
}

_DEFAULT_CONFIG: dict = {
    "speech":  {"rate": 0, "volume": 100, "voice": ""},
    "startup": {"announce_ready": True},
    "window":  {"announce_class": True, "announce_title": False, "max_title_length": 40},
    "monitor": {"announce_monitor": "auto"},
    "events":  _DEFAULT_EVENTS,
}

_DEFAULT_CONFIG_TOML = """\
[speech]
rate = 0
volume = 100
voice = ""

[startup]
announce_ready = true

[window]
announce_class = true
announce_title = false
max_title_length = 40

[monitor]
# "always", "never", or "auto" (include monitor name only if >1 monitor detected)
announce_monitor = "auto"

[events.focus]
enabled = true
priority = "high"

[events.open_window]
enabled = true
priority = "normal"

[events.close_window]
enabled = true
priority = "normal"

[events.workspace]
enabled = true
priority = "high"

[events.move_window]
enabled = false
priority = "low"

[events.fullscreen]
enabled = true
priority = "normal"

[events.urgent]
enabled = true
priority = "critical"

[events.focused_monitor]
enabled = false
priority = "low"
"""


@dataclass
class EventConfig:
    enabled: bool
    priority: str  # "critical", "high", "normal", "low"


@dataclass
class Config:
    speech_rate: int
    speech_volume: int
    speech_voice: str
    startup_announce_ready: bool
    window_announce_class: bool
    window_announce_title: bool
    window_max_title_length: int
    monitor_announce: str  # "always", "never", "auto"
    events: dict[str, EventConfig]


def load_config(path: Path = CONFIG_PATH) -> Config:
    """Load config from TOML, falling back to defaults for any missing key."""
    raw: dict = {}
    if path.exists():
        with open(path, "rb") as f:
            raw = tomllib.load(f)

    def _get(section: str, key: str):
        return raw.get(section, {}).get(key, _DEFAULT_CONFIG[section][key])

    events: dict[str, EventConfig] = {}
    for name, defaults in _DEFAULT_EVENTS.items():
        ev_raw = raw.get("events", {}).get(name, {})
        events[name] = EventConfig(
            enabled=ev_raw.get("enabled", defaults["enabled"]),
            priority=ev_raw.get("priority", defaults["priority"]),
        )

    return Config(
        speech_rate=_get("speech", "rate"),
        speech_volume=_get("speech", "volume"),
        speech_voice=_get("speech", "voice"),
        startup_announce_ready=_get("startup", "announce_ready"),
        window_announce_class=_get("window", "announce_class"),
        window_announce_title=_get("window", "announce_title"),
        window_max_title_length=_get("window", "max_title_length"),
        monitor_announce=_get("monitor", "announce_monitor"),
        events=events,
    )


def write_default_config(path: Path = CONFIG_PATH) -> None:
    """Write a default config file. Creates parent directories if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_DEFAULT_CONFIG_TOML)
