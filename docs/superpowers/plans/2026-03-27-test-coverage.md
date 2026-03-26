# Test Coverage Improvement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 4 broken tests caused by session changes to `ipc.py` and `speech.py`, then add tests to reach ≥95% overall coverage.

**Architecture:** All work is purely in the test layer — `tests/conftest.py`, `tests/test_ipc.py`, `tests/test_speech.py`, `tests/test_events.py`, `tests/test_query.py`, `tests/test_main.py` — plus minimal `# pragma: no cover` markers on untestable daemon internals in `hyprtalk/__main__.py`.

**Tech Stack:** pytest, pytest-asyncio (`asyncio_mode = "auto"` — no `@pytest.mark.asyncio` needed), `unittest.mock`, `importlib.reload`

---

## File Map

| File | Change |
|------|--------|
| `tests/conftest.py` | Replace `PriorityId` mock with `Priority` |
| `tests/test_ipc.py` | Fix 3 broken tests; add 6 new tests |
| `tests/test_speech.py` | Fix 1 broken test; add 3 new tests |
| `tests/test_events.py` | Add 10 new tests |
| `tests/test_query.py` | Add 4 new tests |
| `tests/test_main.py` | Add 1 new test |
| `hyprtalk/__main__.py` | Add `# pragma: no cover` to 3 untestable blocks |

---

## Task 1: Fix conftest.py — PriorityId → Priority

The real `speechd` API uses `speechd.Priority`, not `speechd.PriorityId`. The mock must match.

**Files:**
- Modify: `tests/conftest.py`

- [ ] **Step 1: Update the mock setup**

Replace the four `PriorityId` lines with `Priority`:

```python
import sys
from pathlib import Path
from unittest.mock import MagicMock
import pytest

# Mock speechd BEFORE any imports (conftest is loaded before tests)
_mock_speechd = MagicMock()
_mock_speechd.Priority.IMPORTANT = "IMPORTANT"
_mock_speechd.Priority.MESSAGE = "MESSAGE"
_mock_speechd.Priority.TEXT = "TEXT"
_mock_speechd.Priority.NOTIFICATION = "NOTIFICATION"
sys.modules["speechd"] = _mock_speechd


@pytest.fixture(autouse=True)
def mock_speechd():
    """Mock speechd module — requires running speech-dispatcher, not available in tests."""
    # Reset the mock for each test
    _mock_speechd.reset_mock()
    _mock_speechd.Client.side_effect = None
    _mock_speechd.Priority.IMPORTANT = "IMPORTANT"
    _mock_speechd.Priority.MESSAGE = "MESSAGE"
    _mock_speechd.Priority.TEXT = "TEXT"
    _mock_speechd.Priority.NOTIFICATION = "NOTIFICATION"
    yield _mock_speechd


@pytest.fixture
def tmp_config_dir(tmp_path):
    d = tmp_path / "config" / "hyprtalk"
    d.mkdir(parents=True)
    return d


@pytest.fixture
def tmp_data_dir(tmp_path):
    d = tmp_path / "share" / "hyprtalk"
    d.mkdir(parents=True)
    return d
```

- [ ] **Step 2: Run tests — expect 3 failures (ipc) + 0 speech failures**

```bash
uv run pytest tests/test_speech.py tests/test_ipc.py -v --tb=short --no-cov
```

Expected: `test_say_maps_priority_to_speechd_constant` now passes; 3 ipc tests still fail.

- [ ] **Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "test: fix mock speechd — use Priority instead of PriorityId"
```

---

## Task 2: Fix test_ipc.py — 3 broken tests

**Files:**
- Modify: `tests/test_ipc.py`

The three broken tests patch `_HYPR_BASE` (removed) and assert the old command wire format.

- [ ] **Step 1: Replace the two socket-dir tests**

The tests must patch `_hypr_base` (a function) rather than the removed `_HYPR_BASE` constant, and the query test must expect the new `j/command` format:

```python
import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from hyprtalk.ipc import get_socket_dir, query, stream_events, _format_command


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
    import time; time.sleep(0.01)
    new.touch()
    with patch("hyprtalk.ipc._hypr_base", return_value=hypr_dir):
        result = get_socket_dir()
    assert result == new


async def test_query_sends_command_returns_response():
    reader = asyncio.StreamReader()
    reader.feed_data(b'{"address": "0x1"}')
    reader.feed_eof()
    writer = AsyncMock()

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
```

- [ ] **Step 2: Run the ipc tests — expect all 5 to pass**

```bash
uv run pytest tests/test_ipc.py -v --tb=short --no-cov
```

Expected: 5 passed, 0 failed.

- [ ] **Step 3: Commit**

```bash
git add tests/test_ipc.py
git commit -m "test: fix ipc tests after _HYPR_BASE removal and j/command protocol change"
```

---

## Task 3: Fix test_speech.py — 1 broken test

**Files:**
- Modify: `tests/test_speech.py`

- [ ] **Step 1: Update the assertion from PriorityId to Priority**

Find and replace only the one broken assertion:

```python
def test_say_maps_priority_to_speechd_constant(mock_speechd, tmp_path):
    speaker = make_speaker(mock_speechd, tmp_path)
    speaker.say("test", priority="critical")
    mock_client = mock_speechd.Client.return_value
    # set_priority should be called with speechd.Priority.IMPORTANT for "critical"
    args = mock_client.set_priority.call_args[0]
    assert args[0] == mock_speechd.Priority.IMPORTANT
```

- [ ] **Step 2: Run the full suite — expect 0 failures**

```bash
uv run pytest tests/ -v --tb=short --no-cov
```

Expected: 69 passed, 0 failed.

- [ ] **Step 3: Commit**

```bash
git add tests/test_speech.py
git commit -m "test: fix priority assertion — speechd.Priority not speechd.PriorityId"
```

---

## Task 4: New ipc.py tests — _hypr_base, _format_command, get_socket_dir error

**Files:**
- Modify: `tests/test_ipc.py`

Add these tests after the existing ones in the file.

- [ ] **Step 1: Add the new tests**

```python
# --- _hypr_base tests ---

def test_hypr_base_uses_xdg_runtime_dir(tmp_path, monkeypatch):
    hypr_dir = tmp_path / "hypr"
    hypr_dir.mkdir()
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    from hyprtalk.ipc import _hypr_base
    assert _hypr_base() == hypr_dir


def test_hypr_base_falls_back_when_xdg_unset(monkeypatch):
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    from hyprtalk.ipc import _hypr_base
    assert _hypr_base() == Path("/tmp/hypr")


def test_hypr_base_falls_back_when_xdg_hypr_missing(tmp_path, monkeypatch):
    # XDG_RUNTIME_DIR is set but $XDG_RUNTIME_DIR/hypr does not exist
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    from hyprtalk.ipc import _hypr_base
    # tmp_path/hypr was not created — is_dir() returns False
    assert _hypr_base() == Path("/tmp/hypr")


# --- _format_command tests ---

def test_format_command_translates_json_flag():
    assert _format_command("activewindow -j") == b"j/activewindow"


def test_format_command_leaves_plain_command_unchanged():
    assert _format_command("version") == b"version"


# --- get_socket_dir error path ---

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
```

- [ ] **Step 2: Run ipc tests — expect all new tests to pass**

```bash
uv run pytest tests/test_ipc.py -v --tb=short --no-cov
```

Expected: 12 passed, 0 failed.

- [ ] **Step 3: Commit**

```bash
git add tests/test_ipc.py
git commit -m "test: add coverage for _hypr_base, _format_command, get_socket_dir error path"
```

---

## Task 5: New speech.py tests — retry, voice, venv fallback

**Files:**
- Modify: `tests/test_speech.py`

- [ ] **Step 1: Add retry and voice tests**

Append to `tests/test_speech.py`:

```python
def test_speaker_succeeds_on_second_connect_attempt(mock_speechd, tmp_path):
    """_connect retries once; second attempt should succeed and not use fallback."""
    good_client = MagicMock()
    mock_speechd.Client.side_effect = [Exception("first attempt failed"), good_client]
    speaker = Speaker("test", dnd_file=tmp_path / "dnd")
    assert not speaker._use_fallback
    assert speaker._client is good_client


def test_speaker_sets_voice_when_configured(mock_speechd, tmp_path):
    """set_synthesis_voice is called when voice is non-empty."""
    speaker = Speaker("test", voice="Alex", dnd_file=tmp_path / "dnd")
    mock_client = mock_speechd.Client.return_value
    mock_client.set_synthesis_voice.assert_called_once_with("Alex")


def test_speaker_skips_voice_when_empty(mock_speechd, tmp_path):
    """set_synthesis_voice must NOT be called when voice is empty string."""
    speaker = Speaker("test", voice="", dnd_file=tmp_path / "dnd")
    mock_client = mock_speechd.Client.return_value
    mock_client.set_synthesis_voice.assert_not_called()
```

- [ ] **Step 2: Add the venv fallback test**

The import-time fallback (speech.py lines 18–36) only fires when `speechd` is absent from `sys.modules` and `sys.prefix != sys.base_prefix`. We trigger it with `importlib.reload`:

```python
def test_speechd_found_via_venv_fallback(tmp_path, monkeypatch, mock_speechd):
    """Lines 18-36: when speechd is absent but reachable via base_prefix
    site-packages, the module-level fallback sets _speechd."""
    import sys, importlib, hyprtalk.speech as speech_mod

    # Build a minimal fake speechd package in a simulated system site-packages
    ver = f"{sys.version_info.major}.{sys.version_info.minor}"
    fake_site = tmp_path / "lib64" / f"python{ver}" / "site-packages"
    fake_site.mkdir(parents=True)
    pkg = fake_site / "speechd"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("Client = None\nPriority = None\n")

    # Simulate an isolated venv: prefix differs from base_prefix
    monkeypatch.setattr(sys, "prefix", "/fake/venv")
    monkeypatch.setattr(sys, "base_prefix", str(tmp_path))
    # Remove speechd from sys.modules so the first import attempt fails
    monkeypatch.delitem(sys.modules, "speechd", raising=False)

    try:
        importlib.reload(speech_mod)
        assert speech_mod._speechd is not None, \
            "venv fallback should have found speechd in base_prefix site-packages"
    finally:
        # Restore the mock speechd and reload to clean state for subsequent tests
        sys.modules["speechd"] = mock_speechd
        importlib.reload(speech_mod)
```

- [ ] **Step 3: Run speech tests — expect all to pass**

```bash
uv run pytest tests/test_speech.py -v --tb=short --no-cov
```

Expected: 14 passed, 0 failed.

- [ ] **Step 4: Commit**

```bash
git add tests/test_speech.py
git commit -m "test: add coverage for speechd connect retry, voice setting, and venv path fallback"
```

---

## Task 6: New events.py tests — disabled events, focusedmon, exception handler

**Files:**
- Modify: `tests/test_events.py`

The existing `make_config()` always enables all events. We need disabled-event tests for each uncovered handler, plus tests for `_on_focusedmon` (entirely untested) and the exception handler in `run_event_loop`.

- [ ] **Step 1: Add disabled-event and focusedmon tests**

Append to `tests/test_events.py`:

```python
# --- Disabled event tests (covers early-return branches) ---

def test_on_openwindow_disabled_does_not_speak():
    config = make_config()
    config.events["open_window"].enabled = False
    speaker = make_speaker()
    cache = WindowCache()
    _on_openwindow("0x1,1,kitty,terminal", config, speaker, cache, show_monitor=False)
    speaker.say.assert_not_called()


def test_on_openwindow_malformed_data_returns_early():
    """Less than 3 comma-separated parts — handler must return without speaking."""
    config = make_config()
    speaker = make_speaker()
    cache = WindowCache()
    _on_openwindow("0x1,1", config, speaker, cache, show_monitor=False)
    speaker.say.assert_not_called()


def test_on_closewindow_disabled_does_not_speak():
    config = make_config()
    config.events["close_window"].enabled = False
    speaker = make_speaker()
    cache = WindowCache()
    cache.add(WindowInfo("0x1", "kitty", "term", "1"))
    _on_closewindow("0x1", config, speaker, cache, show_monitor=False)
    speaker.say.assert_not_called()


def test_on_workspace_disabled_does_not_speak():
    config = make_config()
    config.events["workspace"].enabled = False
    speaker = make_speaker()
    cache = WindowCache()
    _on_workspace("3", config, speaker, cache, show_monitor=False)
    speaker.say.assert_not_called()


def test_on_movewindow_disabled_does_not_speak():
    config = make_config()
    config.events["move_window"].enabled = False
    speaker = make_speaker()
    cache = WindowCache()
    cache.add(WindowInfo("0x1", "firefox", "GitHub", "1"))
    _on_movewindow("0x1,3", config, speaker, cache, show_monitor=False)
    speaker.say.assert_not_called()


def test_on_fullscreen_disabled_does_not_speak():
    config = make_config()
    config.events["fullscreen"].enabled = False
    speaker = make_speaker()
    cache = WindowCache()
    _on_fullscreen("1", config, speaker, cache, show_monitor=False)
    speaker.say.assert_not_called()


def test_on_urgent_disabled_does_not_speak():
    config = make_config()
    config.events["urgent"].enabled = False
    speaker = make_speaker()
    cache = WindowCache()
    cache.add(WindowInfo("0x1", "discord", "Discord", "2"))
    _on_urgent("0x1", config, speaker, cache, show_monitor=False)
    speaker.say.assert_not_called()


# --- _on_focusedmon (entirely uncovered) ---

def test_on_focusedmon_speaks_monitor_and_workspace():
    config = make_config()
    speaker = make_speaker()
    cache = WindowCache()
    _on_focusedmon("HDMI-A-1,3", config, speaker, cache, show_monitor=False)
    speaker.say.assert_called_once()
    text = speaker.say.call_args[0][0]
    assert "HDMI-A-1" in text
    assert "3" in text


def test_on_focusedmon_disabled_does_not_speak():
    config = make_config()
    config.events["focused_monitor"].enabled = False
    speaker = make_speaker()
    cache = WindowCache()
    _on_focusedmon("HDMI-A-1,3", config, speaker, cache, show_monitor=False)
    speaker.say.assert_not_called()


# --- run_event_loop exception handler ---

async def test_run_event_loop_logs_warning_when_handler_raises():
    """When a handler raises, run_event_loop must log a warning and continue."""
    import logging
    config = make_config()
    speaker = make_speaker()

    async def fake_stream_events(socket_dir=None):
        yield ("workspace", "bad-data")

    def crashing_handler(*args, **kwargs):
        raise RuntimeError("handler crashed")

    with patch("hyprtalk.events.stream_events", fake_stream_events), \
         patch("hyprtalk.events.query", AsyncMock(return_value="[]")), \
         patch.dict("hyprtalk.events._HANDLERS", {"workspace": crashing_handler}), \
         patch("hyprtalk.events.log") as mock_log:
        await run_event_loop([config], speaker, socket_dir=Path("/tmp/test"))

    mock_log.warning.assert_called()
    speaker.say.assert_not_called()
```

- [ ] **Step 2: Run events tests — expect all to pass**

```bash
uv run pytest tests/test_events.py -v --tb=short --no-cov
```

Expected: 36 passed, 0 failed.

- [ ] **Step 3: Commit**

```bash
git add tests/test_events.py
git commit -m "test: add coverage for disabled event paths, _on_focusedmon, and exception handler"
```

---

## Task 7: New query.py tests — JSONDecodeError, empty workspaces, unknown command, _signal_daemon

**Files:**
- Modify: `tests/test_query.py`

- [ ] **Step 1: Add the new tests**

Append to `tests/test_query.py`:

```python
async def test_query_focus_handles_invalid_json():
    """JSONDecodeError in focus command → falls back to empty data → 'No focused window'."""
    config = make_config()
    speaker = make_speaker()
    with patch("hyprtalk.query.ipc_query", AsyncMock(return_value="not valid json {")):
        await run_query("focus", config, speaker)
    assert "no" in speaker.say.call_args[0][0].lower()


async def test_query_workspaces_empty_list():
    """Empty workspace list → speaks 'No workspaces'."""
    config = make_config()
    speaker = make_speaker()
    with patch("hyprtalk.query.ipc_query", AsyncMock(return_value="[]")):
        await run_query("workspaces", config, speaker)
    assert "no" in speaker.say.call_args[0][0].lower()


async def test_query_unknown_command_logs_error(caplog):
    """Unrecognised command → log.error, no speech."""
    import logging
    config = make_config()
    speaker = make_speaker()
    with caplog.at_level(logging.ERROR, logger="hyprtalk.query"):
        await run_query("nonexistent_command", config, speaker)
    assert any("nonexistent_command" in r.message for r in caplog.records)
    speaker.say.assert_not_called()


def test_signal_daemon_silently_ignores_missing_pid_file(tmp_path):
    """_signal_daemon must not raise when PID file does not exist."""
    from hyprtalk.query import _signal_daemon
    with patch("hyprtalk.query.PID_FILE", tmp_path / "no_such.pid"):
        _signal_daemon()  # must not raise


def test_signal_daemon_sends_sigusr1_to_daemon(tmp_path):
    """_signal_daemon reads PID file and sends SIGUSR1."""
    import os, signal
    from hyprtalk.query import _signal_daemon
    pid_file = tmp_path / "hyprtalk.pid"
    pid_file.write_text(str(os.getpid()))
    with patch("hyprtalk.query.PID_FILE", pid_file), \
         patch("hyprtalk.query.os.kill") as mock_kill:
        _signal_daemon()
    mock_kill.assert_called_once_with(os.getpid(), signal.SIGUSR1)
```

- [ ] **Step 2: Run query tests — expect all to pass**

```bash
uv run pytest tests/test_query.py -v --tb=short --no-cov
```

Expected: 20 passed, 0 failed.

- [ ] **Step 3: Commit**

```bash
git add tests/test_query.py
git commit -m "test: add coverage for focus JSONDecodeError, empty workspaces, unknown command, _signal_daemon"
```

---

## Task 8: __main__.py — pragma markers and startup announcement test

**Files:**
- Modify: `hyprtalk/__main__.py`
- Modify: `tests/test_main.py`

Signal handler inner functions and the `__main__` guard require OS-level signal dispatch or process spawning to exercise. Mark them as excluded; add a test for the startup announcement line instead.

- [ ] **Step 1: Add pragma markers to __main__.py**

In `hyprtalk/__main__.py`, add `# pragma: no cover` to three blocks:

```python
    def _shutdown():  # pragma: no cover
        log.info("Shutting down")
        if main_task is not None:
            main_task.cancel()

    def _reload_dnd():  # pragma: no cover
        speaker.reload_dnd()
        log.debug("DND state reloaded from file")
```

And at the bottom:

```python
if __name__ == "__main__":  # pragma: no cover
    main()
```

- [ ] **Step 2: Add startup announcement test**

Append to `tests/test_main.py`:

```python
async def test_run_daemon_announces_ready_on_startup(tmp_path, monkeypatch):
    """When startup_announce_ready=True, daemon speaks 'hyprtalk ready' at start."""
    from hyprtalk.__main__ import _run_daemon

    config = MagicMock()
    config.speech_rate = 0
    config.speech_volume = 100
    config.speech_voice = ""
    config.startup_announce_ready = True
    config.monitor_announce = "never"

    mock_speaker = MagicMock()

    async def fake_event_loop(config_holder, speaker, socket_dir, show_monitor):
        raise asyncio.CancelledError

    monkeypatch.setattr("hyprtalk.__main__.run_event_loop", fake_event_loop)
    monkeypatch.setattr("hyprtalk.__main__.load_config", MagicMock(return_value=config))
    monkeypatch.setattr("hyprtalk.__main__.get_socket_dir", MagicMock(return_value=None))
    monkeypatch.setattr("hyprtalk.__main__.ipc_query", AsyncMock(return_value="[]"))
    monkeypatch.setattr("hyprtalk.__main__.Speaker", MagicMock(return_value=mock_speaker))
    monkeypatch.setattr("hyprtalk.__main__.DATA_DIR", tmp_path)
    monkeypatch.setattr("hyprtalk.__main__.PID_FILE", tmp_path / "hyprtalk.pid")

    await _run_daemon(config)

    mock_speaker.say.assert_called_with("hyprtalk ready", priority="normal")
```

- [ ] **Step 3: Run the full suite with coverage**

```bash
uv run pytest tests/ --tb=short
```

Expected: 0 failures, coverage ≥ 95%.

- [ ] **Step 4: Commit**

```bash
git add hyprtalk/__main__.py tests/test_main.py
git commit -m "test: add startup announcement test; pragma: no cover on untestable signal handler internals"
```

---

## Self-Review

**Spec coverage check:**
- Section 1 (fix 4 broken tests) → Tasks 1–3 ✓
- Section 2 (new ipc tests: `_hypr_base`, `_format_command`, `get_socket_dir` error) → Task 4 ✓
- Section 2 (new speech tests: retry, voice, venv fallback) → Task 5 ✓
- Section 3 (events: disabled paths, focusedmon, exception handler) → Task 6 ✓
- Section 3 (query: JSONDecodeError, empty workspaces, unknown command, `_signal_daemon`) → Task 7 ✓
- Section 3 (__main__: pragma, startup announcement) → Task 8 ✓

**Placeholder scan:** No TBDs, no "implement later", all code blocks complete.

**Type consistency:** `_format_command` imported in Task 4 matches function defined in `ipc.py`. `_signal_daemon` imported in Task 7 matches function in `query.py`. `_on_focusedmon` already imported in `test_events.py` line 11.
