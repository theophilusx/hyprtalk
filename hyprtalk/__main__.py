from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
from pathlib import Path

from hyprtalk.config import load_config, write_default_config, CONFIG_PATH, DATA_DIR, PID_FILE
from hyprtalk.events import run_event_loop
from hyprtalk.ipc import get_socket_dir, query as ipc_query
from hyprtalk.query import run_query
from hyprtalk.speech import Speaker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Hyprland speech feedback daemon"
    )
    parser.add_argument(
        "--query",
        metavar="CMD",
        help=(
            "Run a query command and exit. "
            "Commands: focus, workspace, windows, workspaces, "
            "dnd, dnd-toggle, dnd-on, dnd-off"
        ),
    )
    args = parser.parse_args()

    if not CONFIG_PATH.exists():
        write_default_config()
        log.info("Created default config at %s", CONFIG_PATH)

    config = load_config()

    if args.query:
        speaker = Speaker(
            client_name="hyprtalk-query",
            rate=config.speech_rate,
            volume=config.speech_volume,
            voice=config.speech_voice,
        )
        try:
            asyncio.run(run_query(args.query, config, speaker))
        finally:
            speaker.close()
        return

    # Daemon mode
    asyncio.run(_run_daemon(config))


async def _run_daemon(config) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    socket_dir = get_socket_dir()

    # Detect monitor count for announce_monitor = "auto"
    monitors_json = await ipc_query("monitors -j", socket_dir)
    try:
        monitors = json.loads(monitors_json)
        monitor_count = len(monitors)
    except (json.JSONDecodeError, TypeError):
        monitor_count = 1
    show_monitor = _should_show_monitor(config.monitor_announce, monitor_count)

    speaker = Speaker(
        client_name="hyprtalk",
        rate=config.speech_rate,
        volume=config.speech_volume,
        voice=config.speech_voice,
    )

    # Mutable container so SIGHUP handler can update config seen by the event loop
    config_holder = [config]

    loop = asyncio.get_running_loop()
    main_task: asyncio.Task | None = None

    def _shutdown():
        log.info("Shutting down")
        if main_task is not None:
            main_task.cancel()

    def _reload_dnd():
        speaker.reload_dnd()
        log.debug("DND state reloaded from file")

    def _reload_config():
        config_holder[0] = load_config()
        log.info("Config reloaded")

    loop.add_signal_handler(signal.SIGTERM, _shutdown)
    loop.add_signal_handler(signal.SIGINT,  _shutdown)
    loop.add_signal_handler(signal.SIGUSR1, _reload_dnd)
    loop.add_signal_handler(signal.SIGHUP,  _reload_config)

    PID_FILE.write_text(str(os.getpid()))
    log.info("hyprtalk daemon started (PID %d)", os.getpid())

    if config_holder[0].startup_announce_ready:
        speaker.say("hyprtalk ready", priority="normal")

    main_task = asyncio.current_task()
    try:
        await run_event_loop(config_holder, speaker, socket_dir, show_monitor)
    except asyncio.CancelledError:
        log.info("Event loop cancelled")
    except Exception as e:
        log.error("Event loop exited: %s", e)
    finally:
        PID_FILE.unlink(missing_ok=True)
        speaker.close()


def _should_show_monitor(setting: str, monitor_count: int) -> bool:
    if setting == "always":
        return True
    if setting == "never":
        return False
    return monitor_count > 1  # "auto"


if __name__ == "__main__":
    main()
