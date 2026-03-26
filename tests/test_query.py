import json
import os
import signal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call
import pytest
from hyprtalk.config import Config, EventConfig
from hyprtalk.query import run_query


def make_config() -> Config:
    events = {k: EventConfig(enabled=True, priority="high") for k in [
        "focus","open_window","close_window","workspace",
        "move_window","fullscreen","urgent","focused_monitor",
    ]}
    return Config(
        speech_rate=0, speech_volume=100, speech_voice="",
        startup_announce_ready=True,
        window_announce_class=True, window_announce_title=False, window_max_title_length=40,
        monitor_announce="auto", events=events,
    )


def make_speaker(dnd: bool = False) -> MagicMock:
    speaker = MagicMock()
    speaker.dnd = dnd
    return speaker


async def test_query_focus_speaks_active_window():
    config = make_config()
    speaker = make_speaker()
    window = {"class": "firefox", "title": "GitHub", "workspace": {"id": 1, "name": "1"}}
    with patch("hyprtalk.query.ipc_query", AsyncMock(return_value=json.dumps(window))):
        await run_query("focus", config, speaker)
    speaker.say.assert_called_once()
    assert "firefox" in speaker.say.call_args[0][0].lower()


async def test_query_focus_no_window():
    config = make_config()
    speaker = make_speaker()
    with patch("hyprtalk.query.ipc_query", AsyncMock(return_value="{}")):
        await run_query("focus", config, speaker)
    speaker.say.assert_called_once()
    assert "no" in speaker.say.call_args[0][0].lower()


async def test_query_workspace_speaks_current():
    config = make_config()
    speaker = make_speaker()
    ws = {"id": 3, "name": "3"}
    with patch("hyprtalk.query.ipc_query", AsyncMock(return_value=json.dumps(ws))):
        await run_query("workspace", config, speaker)
    text = speaker.say.call_args[0][0]
    assert "3" in text


async def test_query_workspace_handles_bad_ipc_response():
    config = make_config()
    speaker = make_speaker()
    with patch("hyprtalk.query.ipc_query", AsyncMock(return_value="error: not available")):
        await run_query("workspace", config, speaker)
    speaker.say.assert_called_once()
    text = speaker.say.call_args[0][0].lower()
    assert "unavailable" in text or "error" in text or "unknown" in text


async def test_query_windows_groups_by_workspace():
    config = make_config()
    speaker = make_speaker()
    clients = [
        {"class": "firefox", "title": "gh", "workspace": {"name": "1"}},
        {"class": "kitty",   "title": "t",  "workspace": {"name": "1"}},
        {"class": "thunar",  "title": "fm", "workspace": {"name": "2"}},
    ]
    with patch("hyprtalk.query.ipc_query", AsyncMock(return_value=json.dumps(clients))):
        await run_query("windows", config, speaker)
    text = speaker.say.call_args[0][0]
    assert "firefox" in text.lower()
    assert "kitty" in text.lower()
    assert "thunar" in text.lower()


async def test_query_windows_no_windows():
    config = make_config()
    speaker = make_speaker()
    with patch("hyprtalk.query.ipc_query", AsyncMock(return_value="[]")):
        await run_query("windows", config, speaker)
    assert "no" in speaker.say.call_args[0][0].lower()


async def test_query_workspaces_lists_all():
    config = make_config()
    speaker = make_speaker()
    wss = [
        {"name": "1", "windows": 2},
        {"name": "2", "windows": 1},
    ]
    with patch("hyprtalk.query.ipc_query", AsyncMock(return_value=json.dumps(wss))):
        await run_query("workspaces", config, speaker)
    text = speaker.say.call_args[0][0]
    assert "1" in text and "2" in text


async def test_query_workspaces_handles_bad_ipc_response():
    config = make_config()
    speaker = make_speaker()
    with patch("hyprtalk.query.ipc_query", AsyncMock(return_value="error: not available")):
        await run_query("workspaces", config, speaker)
    speaker.say.assert_called_once()
    text = speaker.say.call_args[0][0].lower()
    assert "unavailable" in text or "error" in text or "unknown" in text


async def test_query_dnd_reports_off(tmp_path):
    config = make_config()
    speaker = make_speaker(dnd=False)
    await run_query("dnd", config, speaker)
    text = speaker.say.call_args[0][0]
    assert "off" in text.lower()
    assert speaker.say.call_args[1].get("bypass_dnd") is True


async def test_query_dnd_reports_on(tmp_path):
    config = make_config()
    speaker = make_speaker(dnd=True)
    await run_query("dnd", config, speaker)
    text = speaker.say.call_args[0][0]
    assert "on" in text.lower()


async def test_query_dnd_toggle_flips_state(tmp_path):
    config = make_config()
    speaker = make_speaker(dnd=False)
    with patch("hyprtalk.query.DND_FILE", tmp_path / "dnd"), \
         patch("hyprtalk.query._signal_daemon"):
        await run_query("dnd-toggle", config, speaker)
    assert speaker.dnd is True
    text = speaker.say.call_args[0][0]
    assert "on" in text.lower()
    assert speaker.say.call_args[1].get("bypass_dnd") is True


async def test_query_dnd_on_enables(tmp_path):
    config = make_config()
    speaker = make_speaker(dnd=False)
    with patch("hyprtalk.query.DND_FILE", tmp_path / "dnd"), \
         patch("hyprtalk.query._signal_daemon"):
        await run_query("dnd-on", config, speaker)
    assert speaker.dnd is True


async def test_query_dnd_off_disables(tmp_path):
    config = make_config()
    speaker = make_speaker(dnd=True)
    with patch("hyprtalk.query.DND_FILE", tmp_path / "dnd"), \
         patch("hyprtalk.query._signal_daemon"):
        await run_query("dnd-off", config, speaker)
    assert speaker.dnd is False


async def test_query_dnd_toggle_writes_file(tmp_path):
    config = make_config()
    speaker = make_speaker(dnd=False)
    dnd_file = tmp_path / "dnd"
    with patch("hyprtalk.query.DND_FILE", dnd_file), \
         patch("hyprtalk.query._signal_daemon"):
        await run_query("dnd-toggle", config, speaker)
    assert dnd_file.read_text() == "on"


async def test_query_dnd_toggle_signals_daemon(tmp_path):
    config = make_config()
    speaker = make_speaker(dnd=False)
    with patch("hyprtalk.query.DND_FILE", tmp_path / "dnd"), \
         patch("hyprtalk.query._signal_daemon") as mock_signal:
        await run_query("dnd-toggle", config, speaker)
    mock_signal.assert_called_once()
