import sys
from pathlib import Path
from unittest.mock import MagicMock
import pytest


@pytest.fixture(autouse=True)
def mock_speechd():
    """Mock speechd module — requires running speech-dispatcher, not available in tests."""
    mock = MagicMock()
    mock.PriorityId.IMPORTANT = "IMPORTANT"
    mock.PriorityId.MESSAGE = "MESSAGE"
    mock.PriorityId.TEXT = "TEXT"
    mock.PriorityId.NOTIFICATION = "NOTIFICATION"
    sys.modules["speechd"] = mock
    yield mock


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
