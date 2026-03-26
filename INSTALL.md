# Installing hyprtalk

## Requirements

- Hyprland 0.48+
- speech-dispatcher (`sudo dnf install speech-dispatcher`)
- Python 3.11+ and uv (`pip install uv` or see https://docs.astral.sh/uv/)

## Install

```bash
git clone <repo> hyprtalk
cd hyprtalk
uv tool install .
```

This places `hyprtalk` at `~/.local/bin/hyprtalk`. Ensure `~/.local/bin` is on your `PATH`.

If `speechd` fails to install via uv (it requires the speech-dispatcher C library), install
the system package instead and allow uv to use it:

```bash
sudo dnf install python3-speechd
```

Then add to `pyproject.toml`:
```toml
[tool.uv]
system-site-packages = true
```

And reinstall: `uv tool install .`

## Configure Systemd

```bash
mkdir -p ~/.config/systemd/user
cp hyprtalk.service ~/.config/systemd/user/
systemctl --user daemon-reload
```

The unit is **not enabled** — it is started exclusively by Hyprland's `exec-once`.
This ensures hyprtalk only runs during a Hyprland session.

## Add to hyprland.conf

**Standard Hyprland:**
```ini
exec-once = systemctl --user start hyprtalk
```

**UWSM users** (if you launch Hyprland via uwsm):
```ini
exec-once = uwsm app -- systemctl --user start hyprtalk
```

## Keybindings (add to hyprland.conf)

```ini
bind = $mod, F1, exec, hyprtalk --query focus
bind = $mod, F2, exec, hyprtalk --query workspace
bind = $mod, F3, exec, hyprtalk --query windows
bind = $mod, F4, exec, hyprtalk --query workspaces
bind = $mod SHIFT, F1, exec, hyprtalk --query dnd-toggle
```

## Manual Control

```bash
systemctl --user start hyprtalk
systemctl --user stop hyprtalk
systemctl --user restart hyprtalk
journalctl --user -u hyprtalk -f
```

## Configuration

On first run, hyprtalk creates `~/.config/hyprtalk/config.toml` with defaults.
Edit that file to adjust verbosity, speech rate, and which events are announced.
Send SIGHUP to reload config without restarting:

```bash
systemctl --user kill --signal=SIGHUP hyprtalk
```
