import sys
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from hyprtalk.__main__ import _should_show_monitor, main


def test_should_show_monitor_always():
    assert _should_show_monitor("always", 1) is True
    assert _should_show_monitor("always", 3) is True


def test_should_show_monitor_never():
    assert _should_show_monitor("never", 1) is False
    assert _should_show_monitor("never", 3) is False


def test_should_show_monitor_auto_single():
    assert _should_show_monitor("auto", 1) is False


def test_should_show_monitor_auto_multi():
    assert _should_show_monitor("auto", 2) is True


def test_main_query_mode_dispatches_and_exits(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["hyprtalk", "--query", "focus"])
    mock_speaker = MagicMock()
    mock_speaker.dnd = False

    with patch("hyprtalk.__main__.load_config") as mock_cfg, \
         patch("hyprtalk.__main__.Speaker", return_value=mock_speaker), \
         patch("hyprtalk.__main__.run_query", AsyncMock()) as mock_query:
        mock_cfg.return_value = MagicMock(
            speech_rate=0, speech_volume=100, speech_voice=""
        )
        main()

    mock_query.assert_called_once()
    args = mock_query.call_args[0]
    assert args[0] == "focus"
    mock_speaker.close.assert_called_once()


async def test_run_daemon_sighup_propagates_config_to_event_loop(tmp_path, monkeypatch):
    """SIGHUP reload must update the config seen by the event loop."""
    import os, asyncio, signal
    from hyprtalk.__main__ import _run_daemon
    from hyprtalk.config import Config

    base_config = MagicMock()
    base_config.speech_rate = 0
    base_config.speech_volume = 100
    base_config.speech_voice = ""
    base_config.startup_announce_ready = False
    base_config.monitor_announce = "never"

    new_config = MagicMock()
    new_config.startup_announce_ready = False

    seen_configs = []

    async def fake_event_loop(config_holder, speaker, socket_dir, show_monitor):
        before = config_holder[0]
        os.kill(os.getpid(), signal.SIGHUP)
        await asyncio.sleep(0.01)  # yield so signal handler runs
        after = config_holder[0]
        seen_configs.append((before, after))
        raise asyncio.CancelledError

    monkeypatch.setattr("hyprtalk.__main__.run_event_loop", fake_event_loop)
    monkeypatch.setattr("hyprtalk.__main__.load_config", MagicMock(side_effect=[new_config]))
    monkeypatch.setattr("hyprtalk.__main__.get_socket_dir", MagicMock(return_value=None))
    monkeypatch.setattr("hyprtalk.__main__.ipc_query", AsyncMock(return_value="[]"))
    monkeypatch.setattr("hyprtalk.__main__.Speaker", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr("hyprtalk.__main__.DATA_DIR", tmp_path)
    monkeypatch.setattr("hyprtalk.__main__.PID_FILE", tmp_path / "hyprtalk.pid")

    await _run_daemon(base_config)

    # After SIGHUP, config_holder[0] must be the new config
    assert len(seen_configs) == 1
    before, after = seen_configs[0]
    assert before is base_config
    assert after is new_config


async def test_run_daemon_monitor_detection_handles_socket_error(tmp_path, monkeypatch):
    """Socket error during monitor query must not crash daemon startup."""
    from hyprtalk.__main__ import _run_daemon

    config = MagicMock()
    config.speech_rate = 0
    config.speech_volume = 100
    config.speech_voice = ""
    config.startup_announce_ready = False
    config.monitor_announce = "auto"

    async def fake_event_loop(config_holder, speaker, socket_dir, show_monitor):
        assert show_monitor is False  # auto with count=1 → False
        raise asyncio.CancelledError

    monkeypatch.setattr("hyprtalk.__main__.run_event_loop", fake_event_loop)
    monkeypatch.setattr("hyprtalk.__main__.load_config", MagicMock(return_value=config))
    monkeypatch.setattr("hyprtalk.__main__.get_socket_dir", MagicMock(return_value=None))
    monkeypatch.setattr(
        "hyprtalk.__main__.ipc_query",
        AsyncMock(side_effect=OSError("socket not found")),
    )
    monkeypatch.setattr("hyprtalk.__main__.Speaker", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr("hyprtalk.__main__.DATA_DIR", tmp_path)
    monkeypatch.setattr("hyprtalk.__main__.PID_FILE", tmp_path / "hyprtalk.pid")

    await _run_daemon(config)
