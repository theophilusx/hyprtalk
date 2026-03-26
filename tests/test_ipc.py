import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from hyprtalk.ipc import get_socket_dir, query, stream_events, _format_command, _hypr_base


def test_get_socket_dir_uses_env_var(tmp_path, monkeypatch):
    fake_sig = "abc123_111_222"
    hypr_dir = tmp_path / "hypr" / fake_sig
    hypr_dir.mkdir(parents=True)
    monkeypatch.setenv("HYPRLAND_INSTANCE_SIGNATURE", fake_sig)
    with patch("hyprtalk.ipc._hypr_base", return_value=tmp_path / "hypr"):
        result = get_socket_dir()
    assert result == hypr_dir


def test_get_socket_dir_falls_back_to_newest_instance(tmp_path, monkeypatch):
    monkeypatch.delenv("HYPRLAND_INSTANCE_SIGNATURE", raising=False)
    hypr_dir = tmp_path / "hypr"
    hypr_dir.mkdir()
    old = hypr_dir / "old_instance"
    new = hypr_dir / "new_instance"
    old.mkdir()
    new.mkdir()
    # Make new_instance newer by touching it
    import time; time.sleep(0.01)
    new.touch()
    with patch("hyprtalk.ipc._hypr_base", return_value=hypr_dir):
        result = get_socket_dir()
    assert result == new


async def test_query_sends_command_returns_response():
    reader = asyncio.StreamReader()
    reader.feed_data(b'{"address": "0x1"}')
    reader.feed_eof()
    writer = MagicMock()
    writer.drain = AsyncMock()
    writer.wait_closed = AsyncMock()

    with patch("hyprtalk.ipc.open_unix_connection", return_value=(reader, writer)):
        result = await query("activewindow -j", socket_dir=Path("/tmp/test"))

    writer.write.assert_called_once_with(b"j/activewindow")
    assert result == '{"address": "0x1"}'


async def test_stream_events_yields_parsed_events():
    reader = asyncio.StreamReader()
    reader.feed_data(
        b"activewindow>>firefox,GitHub\n"
        b"workspace>>3\n"
    )
    reader.feed_eof()
    writer = MagicMock()
    writer.wait_closed = AsyncMock()

    with patch("hyprtalk.ipc.open_unix_connection", return_value=(reader, writer)):
        events = []
        async for name, data in stream_events(socket_dir=Path("/tmp/test")):
            events.append((name, data))

    assert events == [
        ("activewindow", "firefox,GitHub"),
        ("workspace", "3"),
    ]


async def test_stream_events_skips_malformed_lines():
    reader = asyncio.StreamReader()
    reader.feed_data(b"malformed_line_no_separator\nworkspace>>5\n")
    reader.feed_eof()
    writer = MagicMock()
    writer.wait_closed = AsyncMock()

    with patch("hyprtalk.ipc.open_unix_connection", return_value=(reader, writer)):
        events = []
        async for name, data in stream_events(socket_dir=Path("/tmp/test")):
            events.append((name, data))

    assert events == [("workspace", "5")]


# --- _hypr_base tests ---

def test_hypr_base_uses_xdg_runtime_dir(tmp_path, monkeypatch):
    hypr_dir = tmp_path / "hypr"
    hypr_dir.mkdir()
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    # _hypr_base reads environment on each call
    assert _hypr_base() == hypr_dir


def test_hypr_base_falls_back_when_xdg_unset(monkeypatch):
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    assert _hypr_base() == Path("/tmp/hypr")


def test_hypr_base_falls_back_when_xdg_hypr_missing(tmp_path, monkeypatch):
    # XDG_RUNTIME_DIR is set but $XDG_RUNTIME_DIR/hypr does not exist
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    # tmp_path/hypr was not created — is_dir() returns False
    assert _hypr_base() == Path("/tmp/hypr")


# --- _format_command tests ---

def test_format_command_translates_json_flag():
    assert _format_command("activewindow -j") == b"j/activewindow"


def test_format_command_leaves_plain_command_unchanged():
    assert _format_command("version") == b"version"


# --- get_socket_dir error paths ---

def test_get_socket_dir_raises_when_base_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("HYPRLAND_INSTANCE_SIGNATURE", raising=False)
    missing = tmp_path / "no_such_hypr"
    with patch("hyprtalk.ipc._hypr_base", return_value=missing):
        with pytest.raises(RuntimeError, match="No Hyprland socket directory"):
            get_socket_dir()


def test_get_socket_dir_raises_when_no_instances(tmp_path, monkeypatch):
    monkeypatch.delenv("HYPRLAND_INSTANCE_SIGNATURE", raising=False)
    empty_hypr = tmp_path / "hypr"
    empty_hypr.mkdir()
    with patch("hyprtalk.ipc._hypr_base", return_value=empty_hypr):
        with pytest.raises(RuntimeError, match="No Hyprland instances"):
            get_socket_dir()
