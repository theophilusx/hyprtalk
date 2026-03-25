import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from hyprtalk.ipc import get_socket_dir, query, stream_events


def test_get_socket_dir_uses_env_var(tmp_path, monkeypatch):
    fake_sig = "abc123_111_222"
    hypr_dir = tmp_path / "hypr" / fake_sig
    hypr_dir.mkdir(parents=True)
    monkeypatch.setenv("HYPRLAND_INSTANCE_SIGNATURE", fake_sig)
    with patch("hyprtalk.ipc._HYPR_BASE", tmp_path / "hypr"):
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
    with patch("hyprtalk.ipc._HYPR_BASE", hypr_dir):
        result = get_socket_dir()
    assert result == new


async def test_query_sends_command_returns_response():
    reader = asyncio.StreamReader()
    reader.feed_data(b'{"address": "0x1"}')
    reader.feed_eof()
    writer = AsyncMock()

    with patch("hyprtalk.ipc.open_unix_connection", return_value=(reader, writer)):
        result = await query("activewindow -j", socket_dir=Path("/tmp/test"))

    writer.write.assert_called_once_with(b"activewindow -j")
    assert result == '{"address": "0x1"}'


async def test_stream_events_yields_parsed_events():
    reader = asyncio.StreamReader()
    reader.feed_data(
        b"activewindow>>firefox,GitHub\n"
        b"workspace>>3\n"
    )
    reader.feed_eof()
    writer = AsyncMock()

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
    writer = AsyncMock()

    with patch("hyprtalk.ipc.open_unix_connection", return_value=(reader, writer)):
        events = []
        async for name, data in stream_events(socket_dir=Path("/tmp/test")):
            events.append((name, data))

    assert events == [("workspace", "5")]
