from __future__ import annotations

import logging
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

PRIORITY_MAP: dict[str, str] = {
    "critical": "IMPORTANT",
    "high":     "MESSAGE",
    "normal":   "TEXT",
    "low":      "NOTIFICATION",
}

try:
    import speechd as _speechd
except ImportError:
    # speechd (python3-speechd on Fedora/Debian) is a system-only package not
    # available on PyPI.  When hyprtalk runs inside an isolated uv tool
    # environment, sys.base_prefix still points to the system Python root, so
    # we can locate the system site-packages and retry the import from there.
    import sys as _sys
    _speechd = None  # type: ignore
    if _sys.prefix != _sys.base_prefix:
        _ver = f"{_sys.version_info.major}.{_sys.version_info.minor}"
        for _p in (
            f"{_sys.base_prefix}/lib/python{_ver}/site-packages",
            f"{_sys.base_prefix}/lib64/python{_ver}/site-packages",
        ):
            if _p not in _sys.path:
                _sys.path.append(_p)
        try:
            import speechd as _speechd  # type: ignore
        except ImportError:
            pass


class Speaker:
    """Wraps speech-dispatcher with DND support and spd-say fallback."""

    def __init__(
        self,
        client_name: str = "hyprtalk",
        rate: int = 0,
        volume: int = 100,
        voice: str = "",
        dnd_file: Path | None = None,
    ) -> None:
        from hyprtalk.config import DND_FILE
        self._dnd_file = dnd_file if dnd_file is not None else DND_FILE
        self._dnd = self._read_dnd_file()
        self._client_name = client_name
        self._rate = rate
        self._volume = volume
        self._voice = voice
        self._client = None
        self._use_fallback = False
        self._connect()

    def _connect(self) -> None:
        if _speechd is None:
            log.warning("speechd module not available, using spd-say fallback")
            self._use_fallback = True
            return
        for attempt in range(2):
            try:
                self._client = _speechd.Client(self._client_name)
                self._client.set_rate(self._rate)
                self._client.set_volume(self._volume)
                if self._voice:
                    self._client.set_synthesis_voice(self._voice)
                self._use_fallback = False
                return
            except Exception as e:
                log.warning("speechd connect attempt %d failed: %s", attempt + 1, e)
        log.warning("speechd unavailable, using spd-say fallback")
        self._client = None
        self._use_fallback = True

    def _read_dnd_file(self) -> bool:
        try:
            return self._dnd_file.read_text().strip() == "on"
        except FileNotFoundError:
            return False

    @property
    def dnd(self) -> bool:
        return self._dnd

    @dnd.setter
    def dnd(self, value: bool) -> None:
        self._dnd = value

    def reload_dnd(self) -> None:
        """Re-read DND state from file (called on SIGUSR1)."""
        self._dnd = self._read_dnd_file()

    def say(self, text: str, priority: str = "normal", bypass_dnd: bool = False) -> None:
        """Speak text. Suppressed if DND is on unless bypass_dnd is True."""
        if not text:
            return
        if self._dnd and not bypass_dnd:
            return
        if self._use_fallback:
            subprocess.run(["spd-say", "--", text], check=False)
            return
        spd_priority = PRIORITY_MAP.get(priority, "TEXT")
        try:
            self._client.set_priority(getattr(_speechd.Priority, spd_priority))
            self._client.say(text)
        except Exception as e:
            log.error("speechd say failed: %s — falling back to spd-say", e)
            subprocess.run(["spd-say", "--", text], check=False)

    def close(self) -> None:
        if self._client is not None and not self._use_fallback:
            try:
                self._client.close()
            except Exception:
                pass
