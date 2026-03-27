from pathlib import Path
from unittest.mock import MagicMock, call, patch
import pytest
from hyprtalk.speech import Speaker, PRIORITY_MAP


def make_speaker(mock_speechd, tmp_path, dnd_state: str | None = None) -> Speaker:
    """Helper: create a Speaker with a mock speechd client."""
    dnd_file = tmp_path / "dnd"
    if dnd_state is not None:
        dnd_file.write_text(dnd_state)
    return Speaker("test", dnd_file=dnd_file)


def test_priority_map_covers_all_levels():
    assert set(PRIORITY_MAP.keys()) == {"critical", "high", "normal", "low"}


def test_say_calls_speechd_with_correct_priority(mock_speechd, tmp_path):
    speaker = make_speaker(mock_speechd, tmp_path)
    speaker.say("Hello world", priority="high")
    mock_client = mock_speechd.Client.return_value
    mock_client.set_priority.assert_called_once()
    mock_client.say.assert_called_once_with("Hello world")


def test_say_maps_priority_to_speechd_constant(mock_speechd, tmp_path):
    speaker = make_speaker(mock_speechd, tmp_path)
    speaker.say("test", priority="critical")
    mock_client = mock_speechd.Client.return_value
    # set_priority should be called with the speechd Priority constant for IMPORTANT
    args = mock_client.set_priority.call_args[0]
    assert args[0] == mock_speechd.Priority.IMPORTANT


def test_say_suppressed_when_dnd_on(mock_speechd, tmp_path):
    speaker = make_speaker(mock_speechd, tmp_path, dnd_state="on")
    speaker.say("Hello", priority="normal")
    mock_client = mock_speechd.Client.return_value
    mock_client.say.assert_not_called()


def test_say_bypass_dnd_speaks_even_when_dnd_on(mock_speechd, tmp_path):
    speaker = make_speaker(mock_speechd, tmp_path, dnd_state="on")
    speaker.say("DND status", priority="high", bypass_dnd=True)
    mock_client = mock_speechd.Client.return_value
    mock_client.say.assert_called_once_with("DND status")


def test_dnd_defaults_off_when_no_file(mock_speechd, tmp_path):
    speaker = make_speaker(mock_speechd, tmp_path)
    assert speaker.dnd is False


def test_dnd_reads_on_from_file(mock_speechd, tmp_path):
    speaker = make_speaker(mock_speechd, tmp_path, dnd_state="on")
    assert speaker.dnd is True


def test_reload_dnd_picks_up_file_change(mock_speechd, tmp_path):
    dnd_file = tmp_path / "dnd"
    dnd_file.write_text("off")
    speaker = Speaker("test", dnd_file=dnd_file)
    assert speaker.dnd is False
    dnd_file.write_text("on")
    speaker.reload_dnd()
    assert speaker.dnd is True


def test_say_empty_string_does_nothing(mock_speechd, tmp_path):
    speaker = make_speaker(mock_speechd, tmp_path)
    speaker.say("", priority="normal")
    mock_client = mock_speechd.Client.return_value
    mock_client.say.assert_not_called()


def test_say_falls_back_to_spd_say_when_speechd_fails(mock_speechd, tmp_path):
    mock_speechd.Client.side_effect = Exception("speechd not running")
    speaker = Speaker("test", dnd_file=tmp_path / "dnd")
    with patch("hyprtalk.speech.subprocess.run") as mock_run:
        speaker.say("Fallback text", priority="normal")
    mock_run.assert_called_once_with(["spd-say", "--", "Fallback text"], check=False)


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


def test_speechd_found_via_venv_fallback(tmp_path, monkeypatch, mock_speechd):
    """Lines 18-36: when speechd is absent but reachable via base_prefix
    site-packages, the module-level fallback sets _speechd."""
    import sys, importlib, hyprtalk.speech as speech_mod

    # Build a minimal fake speechd package in a simulated system site-packages
    ver = f"{sys.version_info.major}.{sys.version_info.minor}"
    fake_site = tmp_path / "lib" / f"python{ver}" / "site-packages"
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
