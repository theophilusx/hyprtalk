# hyprtalk

Speech feedback daemon for the [Hyprland](https://hyprland.org/) Wayland compositor. hyprtalk announces window focus changes, workspace switches, and other compositor events via [speech-dispatcher](https://freebdesktop.org/wiki/Software/SpeechDispatcher), enabling blind and vision-impaired users to navigate the desktop without visual access to the screen.

hyprtalk covers the **compositor layer only** — spoken feedback within individual applications (browsers, terminals, editors) remains those applications' responsibility.

---

## What it announces

| Event | Example announcement |
|---|---|
| Window focus | "Firefox" |
| Window opened | "Kitty opened on workspace 2" |
| Window closed | "Firefox closed" |
| Workspace switch | "Workspace 3" |
| Fullscreen toggle | "Fullscreen on" / "Fullscreen off" |
| Urgent window | "Discord needs attention" |
| Window moved | "Kitty moved to workspace 4" *(disabled by default)* |
| Monitor focus | "Monitor 2, workspace 4" *(disabled by default)* |

---

## Requirements

- **Hyprland** 0.48+
- **speech-dispatcher** 0.12.1+ — `sudo dnf install speech-dispatcher` (Fedora) or equivalent
- **Python** 3.11+
- **uv** — see [docs.astral.sh/uv](https://docs.astral.sh/uv/) for install instructions

---

## Quick start

```bash
git clone https://github.com/theophilusx/hyprtalk
cd hyprtalk
uv tool install .
```

This places the `hyprtalk` binary at `~/.local/bin/hyprtalk`. Ensure `~/.local/bin` is on your `PATH`.

**If speechd fails to install** (it requires the speech-dispatcher C library), install the system package instead:

```bash
sudo dnf install python3-speechd
```

Then add to `pyproject.toml` and reinstall:

```toml
[tool.uv]
system-site-packages = true
```

```bash
uv tool install .
```

Verify the install:

```bash
hyprtalk --query focus
```

This should speak the name of your currently focused window (requires Hyprland to be running).

---

## Start on login

### 1. Install the systemd unit

```bash
mkdir -p ~/.config/systemd/user
cp hyprtalk.service ~/.config/systemd/user/
systemctl --user daemon-reload
```

The unit is intentionally **not enabled** — it is started by Hyprland's `exec-once`, so it only runs during a Hyprland session.

### 2. Add to `hyprland.conf`

**Standard Hyprland:**

```ini
exec-once = systemctl --user start hyprtalk
```

**UWSM users** (Hyprland launched via `uwsm`):

```ini
exec-once = uwsm app -- systemctl --user start hyprtalk
```

### 3. Manage the service

```bash
systemctl --user start hyprtalk
systemctl --user stop hyprtalk
systemctl --user restart hyprtalk
journalctl --user -u hyprtalk -f
```

---

## Keybindings

hyprtalk's `--query` mode lets you ask for the current compositor state on demand. Add these to `hyprland.conf` and adjust to your preferred keys:

```ini
bind = $mod, F1, exec, hyprtalk --query focus       # speak focused window
bind = $mod, F2, exec, hyprtalk --query workspace   # speak current workspace
bind = $mod, F3, exec, hyprtalk --query windows     # list all open windows
bind = $mod, F4, exec, hyprtalk --query workspaces  # list all workspaces
bind = $mod SHIFT, F1, exec, hyprtalk --query dnd-toggle
```

---

## Configuration

On first run, hyprtalk creates `~/.config/hyprtalk/config.toml` with defaults. Edit that file to adjust behaviour. All keys are optional — missing keys fall back to built-in defaults, so a minimal or empty config is valid.

To reload config without restarting the daemon:

```bash
systemctl --user kill --signal=SIGHUP hyprtalk
```

### Full configuration reference

```toml
[speech]
rate = 0        # speech rate: -100 (slowest) to 100 (fastest). 0 = speech-dispatcher default
volume = 100    # speech volume: 0 to 100
voice = ""      # synthesis voice name. Empty = speech-dispatcher default

[startup]
announce_ready = true   # speak "hyprtalk ready" when the daemon starts

[window]
announce_class = true       # speak the application class name (e.g. "Firefox")
announce_title = false      # speak the window title (e.g. "GitHub — Mozilla Firefox")
max_title_length = 40       # truncate titles longer than this many characters. 0 = no limit

[monitor]
# Whether to include the monitor name in workspace and focus announcements.
# Does NOT control the focused_monitor event — see [events.focused_monitor] below.
# "always" = always include monitor name
# "never"  = never include monitor name
# "auto"   = include monitor name only when more than one monitor is detected at startup
announce_monitor = "auto"

# Each event can be independently enabled/disabled and assigned a speech priority.
# Priorities: "critical" (interrupts everything), "high", "normal", "low"

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
enabled = false     # disabled by default — can be noisy
priority = "low"

[events.fullscreen]
enabled = true
priority = "normal"

[events.urgent]
enabled = true
priority = "critical"

[events.focused_monitor]
enabled = false     # disabled by default — announces monitor + workspace on monitor switch
priority = "low"
```

---

## Query commands

Run any query command with `hyprtalk --query <command>`. Each command speaks its result and exits immediately.

| Command | What it speaks |
|---|---|
| `focus` | The currently focused window |
| `workspace` | The currently active workspace |
| `windows` | All open windows, grouped by workspace |
| `workspaces` | All workspaces with their window counts |
| `dnd` | Current do-not-disturb state (on or off) |
| `dnd-toggle` | Toggles DND and speaks the new state |
| `dnd-on` | Enables DND |
| `dnd-off` | Disables DND |

Query commands always speak, even when do-not-disturb is on.

---

## Do not disturb

When DND is enabled, the daemon suppresses all event announcements. You can toggle it with a keybinding:

```ini
bind = $mod SHIFT, F1, exec, hyprtalk --query dnd-toggle
```

DND state persists across daemon restarts — it is stored in `~/.local/share/hyprtalk/dnd`.

---

## Signals

| Signal | Effect |
|---|---|
| `SIGHUP` | Reload `~/.config/hyprtalk/config.toml` without restarting |
| `SIGUSR1` | Re-read DND state from `~/.local/share/hyprtalk/dnd` (sent automatically by `--query dnd-*`) |
| `SIGTERM` / `SIGINT` | Graceful shutdown |

Send a signal via systemd:

```bash
systemctl --user kill --signal=SIGHUP hyprtalk
```

---

## Runtime files

| Path | Purpose |
|---|---|
| `~/.config/hyprtalk/config.toml` | User configuration |
| `~/.local/share/hyprtalk/hyprtalk.pid` | Daemon PID (written on start, removed on exit) |
| `~/.local/share/hyprtalk/dnd` | Do-not-disturb state (`on` or `off`) |
| `~/.config/systemd/user/hyprtalk.service` | Systemd user unit |
