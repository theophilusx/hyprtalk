import sys
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
