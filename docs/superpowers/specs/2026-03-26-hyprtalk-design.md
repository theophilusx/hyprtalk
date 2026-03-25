# hyprtalk Design Spec
_2026-03-26_

## Overview

hyprtalk is a lightweight daemon that provides spoken feedback for the Hyprland Wayland compositor, enabling blind and vision-impaired users to navigate the desktop environment without visual access to the screen. It listens to Hyprland's IPC event stream and announces compositor activity (window focus, workspace changes, window open/close, etc.) via speech-dispatcher. Feedback from individual applications (e.g. screen reader integration within a browser or terminal) remains those applications' responsibility — hyprtalk covers the compositor layer only.

**Target environment:** Fedora 43, Hyprland 0.54.2+, speech-dispatcher 0.12.1+, Python 3.11+

---

## Architecture

hyprtalk is a Python package managed with `uv`. It operates in two modes:

- **Daemon mode** (`hyprtalk`): long-running process that connects to Hyprland's event socket and announces events
- **Query mode** (`hyprtalk --query <cmd>`): short-lived process that queries current compositor state and speaks the result, then exits

Both modes share the same config, speech, and IPC modules.

### Package Layout

```
hyprtalk/
├── __main__.py      # entry point, argument parsing, mode dispatch
├── config.py        # TOML loading, defaults, validation
├── ipc.py           # Hyprland socket connections (event stream + hyprctl queries)
├── speech.py        # speech-dispatcher wrapper (priority, interrupt, rate/volume)
├── events.py        # event parsing, announcement formatting, per-event routing
└── query.py         # on-demand query handlers (windows, focus, workspace, dnd)

pyproject.toml
```

### Runtime Files

| Path | Purpose |
|---|---|
| `~/.config/hyprtalk/config.toml` | User configuration |
| `~/.local/share/hyprtalk/hyprtalk.pid` | Daemon PID (written on startup, removed on exit) |
| `~/.local/share/hyprtalk/dnd` | Do-not-disturb state (`on` or `off`) |
| `~/.config/systemd/user/hyprtalk.service` | Systemd user unit |

### Dependency Flow

`__main__.py` → `events.py` → `ipc.py`, `speech.py`, `config.py`
`__main__.py` → `query.py` → `ipc.py`, `speech.py`, `config.py`

No circular dependencies. Each module has one clear responsibility.

---

## Hyprland IPC

Hyprland exposes two Unix sockets per running instance at `/tmp/hypr/<signature>/`:

- `.socket.sock` — request/response (equivalent to `hyprctl`)
- `.socket2.sock` — event stream, one event per line: `eventname>>data`

The daemon connects to `.socket2.sock` using `asyncio` and reads lines continuously. The instance signature is read from the `$HYPRLAND_INSTANCE_SIGNATURE` environment variable (set by Hyprland for all child processes), with a fallback of scanning `/tmp/hypr/` for the most recent instance.

### Handled Events

| Event | Data format | Default announcement |
|---|---|---|
| `activewindow` | `class,title` | "Firefox" / "Firefox — GitHub" |
| `openwindow` | `address,workspace,class,title` | "Firefox opened on workspace 2" |
| `closewindow` | `address` | "Firefox closed" (class resolved from window cache) |
| `workspace` | `name` | "Workspace 3" |
| `focusedmon` | `monitorName,workspace` | "Monitor 2, workspace 4" (only if `[events.focused_monitor] enabled = true`) |
| `movewindow` | `address,workspace` | "Firefox moved to workspace 2" |
| `fullscreen` | `0` or `1` | "Fullscreen on" / "Fullscreen off" |
| `urgent` | `address` | "Firefox needs attention" |

### Window Cache

The daemon maintains an in-memory map of `address → {class, title, workspace}`. It is populated at startup via `hyprctl clients -j` and kept current by `openwindow` and `closewindow` events. This allows `closewindow` (which only provides an address) to announce the name of the window being closed.

---

## Speech

`speech.py` wraps the `speechd` Python client. The daemon opens a single persistent connection named `"hyprtalk"` at startup. Query mode opens a short-lived connection named `"hyprtalk-query"`.

### Priority Mapping

speech-dispatcher's priority levels map to hyprtalk config names:

| Config name | speechd priority | Default use |
|---|---|---|
| `critical` | `IMPORTANT` | urgent window alerts |
| `high` | `MESSAGE` | focus changes, workspace changes |
| `normal` | `TEXT` | window open/close |
| `low` | `NOTIFICATION` | informational |

speechd's own interrupt behaviour applies: `IMPORTANT` and `MESSAGE` interrupt lower-priority speech automatically. hyprtalk does not manage its own queue.

### Speech Settings

```toml
[speech]
rate = 0          # -100 to 100, speechd default = 0
volume = 100      # 0 to 100
voice = ""        # empty = speechd default
```

### Do Not Disturb

When DND is enabled, the daemon suppresses all speech output. The exception is DND query commands (`dnd`, `dnd-toggle`, `dnd-on`, `dnd-off`), which always speak regardless of DND state.

DND state is stored in `~/.local/share/hyprtalk/dnd` as plain text (`on` or `off`). The query process writes the new state and sends `SIGUSR1` to the daemon (via the PID file). The daemon re-reads the state file on `SIGUSR1`. If the PID file does not exist (daemon not running), the state is still written but no signal is sent — the daemon will read the correct state when it next starts.

### Fallback

If the speechd connection fails, hyprtalk logs the error and retries once. If it fails again, it falls back to invoking `spd-say` as a subprocess. This fallback is used for both daemon and query modes.

---

## Configuration

Location: `~/.config/hyprtalk/config.toml`

If the file does not exist, hyprtalk creates it with defaults on first run. Missing keys always fall back to built-in defaults — a minimal or empty config is valid.

```toml
[speech]
rate = 0
volume = 100
voice = ""

[startup]
announce_ready = true   # speak "hyprtalk ready" on daemon start

[window]
announce_class = true       # speak app class name
announce_title = false      # speak window title
max_title_length = 40       # truncate titles longer than this (0 = no limit)

[monitor]
# Controls whether monitor name/number is included in workspace and focus announcements.
# Does NOT control the focused_monitor event — that is governed by [events.focused_monitor].
# "auto" = include monitor info only when more than one monitor is detected at startup.
announce_monitor = "auto"   # "always", "never", "auto"

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
```

Config is reloaded on `SIGHUP` without restarting the daemon.

---

## Query Commands

Invoked as `hyprtalk --query <command>`. Each command fetches current state via `hyprctl` and speaks the result.

| Command | Speaks |
|---|---|
| `focus` | Current focused window (class/title per config) |
| `workspace` | Current workspace name/number |
| `windows` | All open windows grouped by workspace — e.g. "Workspace 1: Firefox, Kitty. Workspace 2: Thunar" |
| `workspaces` | All active workspaces with window counts |
| `dnd` | "Do not disturb is on" or "Do not disturb is off" (always speaks) |
| `dnd-toggle` | Toggles DND, speaks new state, signals daemon (always speaks) |
| `dnd-on` | Enables DND, speaks confirmation, signals daemon (always speaks) |
| `dnd-off` | Disables DND, speaks confirmation, signals daemon (always speaks) |

Query mode works independently of the daemon — it does not require the daemon to be running.

### Example hyprland.conf Bindings

```ini
bind = $mod, F1, exec, hyprtalk --query focus
bind = $mod, F2, exec, hyprtalk --query workspace
bind = $mod, F3, exec, hyprtalk --query windows
bind = $mod, F4, exec, hyprtalk --query workspaces
bind = $mod SHIFT, F1, exec, hyprtalk --query dnd-toggle
```

---

## Daemon Lifecycle

### Startup Sequence

1. Load config (create default file if missing)
2. Read `$HYPRLAND_INSTANCE_SIGNATURE`; fall back to scanning `/tmp/hypr/`
3. Connect to `.socket2.sock` — retry up to 10 times with 1s delay
4. Query `hyprctl clients -j` to populate window cache
5. Write PID to `~/.local/share/hyprtalk/hyprtalk.pid`
6. Open speechd connection
7. Announce "hyprtalk ready" (if `startup.announce_ready = true`)
8. Enter asyncio event loop

### Signal Handling

| Signal | Action |
|---|---|
| `SIGTERM` / `SIGINT` | Clean shutdown: remove PID file, close speechd connection |
| `SIGUSR1` | Re-read DND state file |
| `SIGHUP` | Reload config file |

### Error Handling

- **Socket disconnect** (e.g. compositor restart): log error, exit cleanly — systemd restarts the service
- **speechd unreachable**: retry once, then fall back to `spd-say` subprocess
- **Malformed event**: log and skip, never crash

---

## Installation & Launch

### Install

```bash
uv tool install .
```

This places `hyprtalk` on PATH via `~/.local/bin`.

### Launch via Hyprland

Add to `hyprland.conf`:

```ini
exec-once = systemctl --user start hyprtalk
```

**UWSM users:** If you use [uwsm](https://github.com/Vladimir-csp/uwsm) to manage Hyprland app launches, use:

```ini
exec-once = uwsm app -- systemctl --user start hyprtalk
```

This ensures hyprtalk is correctly registered within the systemd user session scope that UWSM manages.

### Systemd Unit

Install to `~/.config/systemd/user/hyprtalk.service`:

```ini
[Unit]
Description=Hyprland speech feedback daemon
PartOf=graphical-session.target

[Service]
ExecStart=hyprtalk
Restart=on-failure
RestartSec=3
```

The unit is **not enabled** (`systemctl --user enable` is not used). Hyprland's `exec-once` is the sole trigger. This ensures hyprtalk only runs during a Hyprland session and does not start for other compositors or desktop environments.

After installing the unit file:

```bash
systemctl --user daemon-reload
```

### Manual Control

```bash
systemctl --user start hyprtalk
systemctl --user stop hyprtalk
systemctl --user restart hyprtalk
systemctl --user status hyprtalk
journalctl --user -u hyprtalk -f   # follow logs
```

---

## Out of Scope

- Application-level accessibility (screen reader integration within apps)
- AT-SPI / D-Bus accessibility bus integration
- Braille display support
- Audio cues / earcons (speech only)
- Support for compositors other than Hyprland
