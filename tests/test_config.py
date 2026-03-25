import tomllib
from pathlib import Path
import pytest
from hyprtalk.config import (
    Config, EventConfig, load_config, write_default_config,
)


def test_load_config_returns_defaults_when_file_missing(tmp_path):
    config = load_config(tmp_path / "nonexistent.toml")
    assert config.speech_rate == 0
    assert config.speech_volume == 100
    assert config.speech_voice == ""
    assert config.startup_announce_ready is True
    assert config.window_announce_class is True
    assert config.window_announce_title is False
    assert config.window_max_title_length == 40
    assert config.monitor_announce == "auto"


def test_load_config_events_have_defaults(tmp_path):
    config = load_config(tmp_path / "nonexistent.toml")
    assert config.events["focus"].enabled is True
    assert config.events["focus"].priority == "high"
    assert config.events["open_window"].enabled is True
    assert config.events["close_window"].enabled is True
    assert config.events["workspace"].enabled is True
    assert config.events["move_window"].enabled is False
    assert config.events["fullscreen"].enabled is True
    assert config.events["urgent"].enabled is True
    assert config.events["focused_monitor"].enabled is False


def test_load_config_partial_override(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text('[speech]\nrate = 50\n')
    config = load_config(config_file)
    assert config.speech_rate == 50
    assert config.speech_volume == 100  # default preserved


def test_load_config_event_override(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text('[events.focus]\nenabled = false\npriority = "low"\n')
    config = load_config(config_file)
    assert config.events["focus"].enabled is False
    assert config.events["focus"].priority == "low"
    assert config.events["open_window"].enabled is True  # default preserved


def test_write_default_config_creates_valid_toml(tmp_path):
    config_file = tmp_path / "config.toml"
    write_default_config(config_file)
    assert config_file.exists()
    with open(config_file, "rb") as f:
        data = tomllib.load(f)
    assert data["speech"]["rate"] == 0
    assert data["events"]["focus"]["enabled"] is True
