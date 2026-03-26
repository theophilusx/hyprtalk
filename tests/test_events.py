import json
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from hyprtalk.config import Config, EventConfig
from hyprtalk.events import (
    WindowCache, WindowInfo, format_window,
    _on_activewindow, _on_openwindow, _on_closewindow,
    _on_workspace, _on_movewindow, _on_fullscreen, _on_urgent,
    _on_focusedmon,
)


# --- Helpers ---

def make_config(**overrides) -> Config:
    events = {
        "focus":          EventConfig(enabled=True,  priority="high"),
        "open_window":    EventConfig(enabled=True,  priority="normal"),
        "close_window":   EventConfig(enabled=True,  priority="normal"),
        "workspace":      EventConfig(enabled=True,  priority="high"),
        "move_window":    EventConfig(enabled=True,  priority="low"),
        "fullscreen":     EventConfig(enabled=True,  priority="normal"),
        "urgent":         EventConfig(enabled=True,  priority="critical"),
        "focused_monitor":EventConfig(enabled=True,  priority="low"),
    }
    defaults = dict(
        speech_rate=0, speech_volume=100, speech_voice="",
        startup_announce_ready=True,
        window_announce_class=True, window_announce_title=False, window_max_title_length=40,
        monitor_announce="auto", events=events,
    )
    defaults.update(overrides)
    return Config(**defaults)


def make_speaker():
    speaker = MagicMock()
    speaker.dnd = False
    return speaker


# --- WindowCache tests ---

def test_window_cache_add_and_get():
    cache = WindowCache()
    info = WindowInfo(address="0x1", cls="firefox", title="GitHub", workspace="1")
    cache.add(info)
    assert cache.get("0x1") == info


def test_window_cache_remove_returns_info():
    cache = WindowCache()
    info = WindowInfo(address="0x1", cls="kitty", title="terminal", workspace="2")
    cache.add(info)
    removed = cache.remove("0x1")
    assert removed == info
    assert cache.get("0x1") is None


def test_window_cache_remove_missing_returns_none():
    cache = WindowCache()
    assert cache.remove("0xdead") is None


def test_window_cache_move_updates_workspace():
    cache = WindowCache()
    cache.add(WindowInfo("0x1", "kitty", "term", "1"))
    cache.move("0x1", "3")
    assert cache.get("0x1").workspace == "3"


def test_window_cache_update_from_clients():
    cache = WindowCache()
    clients = [
        {"address": "0x1", "class": "firefox", "title": "GitHub", "workspace": {"name": "1"}},
        {"address": "0x2", "class": "kitty",   "title": "term",   "workspace": {"name": "2"}},
    ]
    cache.update_from_clients(json.dumps(clients))
    assert cache.get("0x1").cls == "firefox"
    assert cache.get("0x2").workspace == "2"


def test_window_cache_all_windows():
    cache = WindowCache()
    cache.add(WindowInfo("0x1", "firefox", "GitHub", "1"))
    cache.add(WindowInfo("0x2", "kitty",   "term",   "2"))
    assert len(cache.all_windows()) == 2


# --- format_window tests ---

def test_format_window_class_only():
    config = make_config(window_announce_class=True, window_announce_title=False)
    assert format_window("Firefox", "Some long title", config) == "Firefox"


def test_format_window_title_only():
    config = make_config(window_announce_class=False, window_announce_title=True)
    assert format_window("Firefox", "GitHub", config) == "GitHub"


def test_format_window_class_and_title():
    config = make_config(window_announce_class=True, window_announce_title=True)
    assert format_window("Firefox", "GitHub", config) == "Firefox, GitHub"


def test_format_window_title_truncated():
    config = make_config(window_announce_class=False, window_announce_title=True, window_max_title_length=10)
    result = format_window("Firefox", "A very long title indeed", config)
    assert len(result) <= 10


def test_format_window_title_not_truncated_when_limit_zero():
    config = make_config(window_announce_class=False, window_announce_title=True, window_max_title_length=0)
    long_title = "x" * 200
    assert format_window("App", long_title, config) == long_title


def test_format_window_returns_empty_when_both_disabled():
    config = make_config(window_announce_class=False, window_announce_title=False)
    assert format_window("Firefox", "title", config) == ""


# --- Event handler tests ---

def test_on_activewindow_announces_focus():
    config = make_config()
    speaker = make_speaker()
    cache = WindowCache()
    _on_activewindow("firefox,GitHub — some page", config, speaker, cache, show_monitor=False)
    speaker.say.assert_called_once()
    args = speaker.say.call_args
    assert "firefox" in args[0][0].lower()


def test_on_activewindow_disabled_does_not_speak():
    config = make_config()
    config.events["focus"].enabled = False
    speaker = make_speaker()
    cache = WindowCache()
    _on_activewindow("firefox,title", config, speaker, cache, show_monitor=False)
    speaker.say.assert_not_called()


def test_on_openwindow_announces_open():
    config = make_config()
    speaker = make_speaker()
    cache = WindowCache()
    _on_openwindow("0x1,1,kitty,terminal", config, speaker, cache, show_monitor=False)
    speaker.say.assert_called_once()
    text = speaker.say.call_args[0][0]
    assert "kitty" in text.lower()
    assert "1" in text


def test_on_closewindow_announces_close_using_cache():
    config = make_config()
    speaker = make_speaker()
    cache = WindowCache()
    cache.add(WindowInfo("0x1", "kitty", "term", "1"))
    _on_closewindow("0x1", config, speaker, cache, show_monitor=False)
    speaker.say.assert_called_once()
    text = speaker.say.call_args[0][0]
    assert "kitty" in text.lower()


def test_on_closewindow_removes_from_cache():
    config = make_config()
    speaker = make_speaker()
    cache = WindowCache()
    cache.add(WindowInfo("0x1", "kitty", "term", "1"))
    _on_closewindow("0x1", config, speaker, cache, show_monitor=False)
    assert cache.get("0x1") is None


def test_on_workspace_announces_workspace():
    config = make_config()
    speaker = make_speaker()
    cache = WindowCache()
    _on_workspace("3", config, speaker, cache, show_monitor=False)
    speaker.say.assert_called_once()
    assert "3" in speaker.say.call_args[0][0]


def test_on_movewindow_updates_cache_and_announces():
    config = make_config()
    speaker = make_speaker()
    cache = WindowCache()
    cache.add(WindowInfo("0x1", "firefox", "GitHub", "1"))
    _on_movewindow("0x1,3", config, speaker, cache, show_monitor=False)
    assert cache.get("0x1").workspace == "3"
    speaker.say.assert_called_once()
    text = speaker.say.call_args[0][0]
    assert "3" in text


def test_on_fullscreen_on():
    config = make_config()
    speaker = make_speaker()
    cache = WindowCache()
    _on_fullscreen("1", config, speaker, cache, show_monitor=False)
    assert "on" in speaker.say.call_args[0][0].lower()


def test_on_fullscreen_off():
    config = make_config()
    speaker = make_speaker()
    cache = WindowCache()
    _on_fullscreen("0", config, speaker, cache, show_monitor=False)
    assert "off" in speaker.say.call_args[0][0].lower()


def test_on_urgent_announces_class_from_cache():
    config = make_config()
    speaker = make_speaker()
    cache = WindowCache()
    cache.add(WindowInfo("0x1", "discord", "Discord", "2"))
    _on_urgent("0x1", config, speaker, cache, show_monitor=False)
    text = speaker.say.call_args[0][0]
    assert "discord" in text.lower()


from unittest.mock import AsyncMock, patch
from hyprtalk.events import run_event_loop


async def test_run_event_loop_handles_events_until_eof():
    config = make_config()
    speaker = make_speaker()

    async def fake_stream_events(socket_dir=None):
        yield ("workspace", "2")
        yield ("activewindow", "kitty,terminal")

    with patch("hyprtalk.events.stream_events", fake_stream_events), \
         patch("hyprtalk.events.query", AsyncMock(return_value="[]")):
        await run_event_loop([config], speaker, socket_dir=Path("/tmp/test"))

    assert speaker.say.call_count == 2


async def test_run_event_loop_ignores_unknown_events():
    config = make_config()
    speaker = make_speaker()

    async def fake_stream_events(socket_dir=None):
        yield ("unknownevent", "somedata")
        yield ("workspace", "5")

    with patch("hyprtalk.events.stream_events", fake_stream_events), \
         patch("hyprtalk.events.query", AsyncMock(return_value="[]")):
        await run_event_loop([config], speaker, socket_dir=Path("/tmp/test"))

    assert speaker.say.call_count == 1  # only workspace event


async def test_run_event_loop_populates_cache_from_clients():
    config = make_config()
    speaker = make_speaker()
    clients = json.dumps([
        {"address": "0x1", "class": "firefox", "title": "GitHub", "workspace": {"name": "1"}}
    ])

    async def fake_stream_events(socket_dir=None):
        # closewindow uses cache populated at startup
        yield ("closewindow", "0x1")

    with patch("hyprtalk.events.stream_events", fake_stream_events), \
         patch("hyprtalk.events.query", AsyncMock(return_value=clients)):
        await run_event_loop([config], speaker, socket_dir=Path("/tmp/test"))

    text = speaker.say.call_args[0][0]
    assert "firefox" in text.lower()
