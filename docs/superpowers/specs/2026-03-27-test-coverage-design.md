# Test Coverage Improvement — Design Spec

**Date:** 2026-03-27
**Scope:** Fix 4 broken tests caused by session changes; add tests for new code; fill coverage gaps across all modules.
**Target:** ≥95% overall coverage, 0 failing tests.

---

## Context

During this session, `ipc.py` and `speech.py` were updated to fix Hyprland socket path/protocol issues and speechd import in isolated venvs. Four existing tests were not updated to match and are now failing. Additionally, new functions (`_hypr_base`, `_format_command`, speechd venv fallback) have zero test coverage.

Current state: **84% coverage, 4 tests failing.**

---

## Section 1: Fix Broken Tests

All four failures are assertion/patch mismatches caused by the code changes this session.

### `tests/test_ipc.py`

**`test_get_socket_dir_uses_env_var` / `test_get_socket_dir_falls_back_to_newest_instance`**
- Currently patch `hyprtalk.ipc._HYPR_BASE` (removed constant)
- Fix: patch `hyprtalk.ipc._hypr_base` as a function returning a controlled `tmp_path`

**`test_query_sends_command_returns_response`**
- Currently asserts `writer.write` called with `b"activewindow -j"`
- Fix: assert `b"j/activewindow"` (new `_format_command` translation)

### `tests/test_speech.py`

**`test_say_maps_priority_to_speechd_constant`**
- Currently checks `mock_speechd.PriorityId.IMPORTANT`
- Fix: check `mock_speechd.Priority.IMPORTANT`

### `tests/conftest.py`

- Currently sets up `_mock_speechd.PriorityId.*` constants
- Fix: set up `_mock_speechd.Priority.*` constants instead (matching real speechd API)

---

## Section 2: New Tests for New Code

### `tests/test_ipc.py` — new tests

| Test | What it covers |
|------|---------------|
| `test_hypr_base_uses_xdg_runtime_dir` | Returns `$XDG_RUNTIME_DIR/hypr` when directory exists |
| `test_hypr_base_falls_back_when_xdg_unset` | Returns `Path("/tmp/hypr")` when env var absent |
| `test_hypr_base_falls_back_when_xdg_hypr_missing` | Returns `/tmp/hypr` when `$XDG_RUNTIME_DIR/hypr` is not a directory |
| `test_format_command_translates_json_flag` | `"activewindow -j"` → `b"j/activewindow"` |
| `test_format_command_leaves_plain_command` | `"version"` → `b"version"` (no `-j`, no translation) |
| `test_get_socket_dir_raises_when_no_instances` | `RuntimeError` when base dir exists but contains no subdirs |

### `tests/test_speech.py` — new tests

| Test | What it covers | Lines |
|------|---------------|-------|
| `test_speaker_connects_on_second_attempt` | `_connect()` succeeds on retry after first exception | 63–65 |
| `test_speaker_sets_voice_when_configured` | `set_synthesis_voice` called when voice is non-empty | 93 |
| `test_speechd_fallback_via_sys_path` | Speechd found via sys.path extension (venv fallback) | 18–36 |

The `test_speechd_fallback_via_sys_path` test temporarily removes `speechd` from `sys.modules`, adds a fake `speechd` module to a temp directory on `sys.path`, manipulates `sys.prefix`/`sys.base_prefix` to simulate a venv, and reimports the module. This is the only way to exercise lines 18–36 which run at import time.

---

## Section 3: Fill Gaps in Existing Modules

### `tests/test_events.py` — new tests

| Test | Handler | Gap covered |
|------|---------|-------------|
| `test_on_closewindow_unknown_address` | `_on_closewindow` | Falls back to `"window"` when address not in cache (line 107) |
| `test_on_movewindow_unknown_address` | `_on_movewindow` | Falls back to `"window"` when address not in cache (line 140) |
| `test_on_urgent_unknown_address` | `_on_urgent` | Falls back to `"window"` when address not in cache (line 166) |
| `test_on_focusedmon_speaks_monitor_and_workspace` | `_on_focusedmon` | Happy path (lines 128–132) |
| `test_on_focusedmon_disabled` | `_on_focusedmon` | Returns early when event disabled (line 120) |
| `test_run_event_loop_logs_handler_exception` | `run_event_loop` | Warning logged when handler raises (lines 215–216) |

### `tests/test_query.py` — new tests

| Test | Gap covered |
|------|-------------|
| `test_signal_daemon_no_pid_file` | `_signal_daemon` silently ignores missing PID file (line 104–108) |
| `test_signal_daemon_sends_sigusr1` | `_signal_daemon` sends SIGUSR1 to valid PID |

### `tests/test_main.py` — additions

| Test | Gap covered |
|------|-------------|
| `test_should_show_monitor_unknown_value_logs_warning` | Unknown `monitor_announce` value logs warning, treated as `"auto"` (lines 92–94, 97–98) |

### `hyprtalk/__main__.py` — pragma exclusions

Mark `_run_daemon` signal handler closures and the `if __name__ == "__main__"` guard with `# pragma: no cover`. These require full async integration test infrastructure to exercise and the risk/value ratio is poor.

---

## Testing Conventions

- `asyncio_mode = "auto"` — no `@pytest.mark.asyncio` decorators needed
- Mock IPC at `ipc.query` / `ipc.stream_events` level, never at socket level
- Use existing fixtures from `conftest.py` before creating new ones
- One test file per source module

---

## Success Criteria

- `uv run pytest` exits 0 (no failures, coverage ≥ 84% threshold passes)
- Coverage reaches ≥ 95% overall
- No `# pragma: no cover` added except for `_run_daemon` internals and `__main__` guard
