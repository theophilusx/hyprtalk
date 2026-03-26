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
    # set_priority should be called with the speechd PriorityId constant for IMPORTANT
    args = mock_client.set_priority.call_args[0]
    assert args[0] == mock_speechd.PriorityId.IMPORTANT


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
