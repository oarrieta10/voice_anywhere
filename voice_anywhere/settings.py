"""Choices made in the tray menu, remembered between runs.

They are kept in %LOCALAPPDATA%\\voice-anywhere\\settings.json, next to the log. A choice
saved here wins over the matching environment variable (for example the tray's Language
menu wins over VOICE_WHISPER_LANG). Only settings live here, never dictated text.
"""
import json
import logging
import os
from pathlib import Path

log = logging.getLogger("voice_anywhere")


def data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    path = Path(base) / "voice-anywhere"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _path() -> Path:
    return data_dir() / "settings.json"


def load() -> dict:
    """The saved settings, or {} if there are none (or the file is damaged)."""
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        log.warning("Ignoring unreadable settings file: %s", exc)
        return {}


def save(**changes) -> None:
    """Update some settings and keep the others."""
    data = load()
    data.update(changes)
    try:
        _path().write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError as exc:
        log.warning("Could not save settings: %s", exc)
