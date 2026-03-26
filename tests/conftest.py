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
