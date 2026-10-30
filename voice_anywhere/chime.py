"""The chime that plays when the microphone is live. Fully offline.

Plays sounds/intuition-561.wav with Windows' built-in sound player, which always uses the
current default speakers. The first SKIP_SECONDS of audio are thrown away (see Recorder)
so that the chime, heard through speakers, is not transcribed. A chime that cannot play
is only logged: dictation carries on without it.
Settings:
  VOICE_CHIME  "on" (default) or "off"; the tray's Chime item wins over it
"""
import logging
import os
import winsound
from pathlib import Path

log = logging.getLogger("voice_anywhere")

SOUND_FILE = Path(__file__).resolve().parent.parent / "sounds" / "intuition-561.wav"
SECONDS = 0.38  # length of the sound
SKIP_SECONDS = SECONDS + 0.05
_choice = None  # set from the tray menu; None means use VOICE_CHIME


def enabled() -> bool:
    if _choice is not None:
        return _choice
    return os.environ.get("VOICE_CHIME", "on").strip().lower() not in ("off", "0", "no", "false")


def set_enabled(on: bool) -> None:
    global _choice
    _choice = on


def skip_seconds() -> float:
    return SKIP_SECONDS if enabled() else 0


def _default_player(path):
    if not path.exists():
        raise FileNotFoundError(path.name)
    winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)


def play(player=_default_player) -> None:
    if not enabled():
        return
    try:
        player(SOUND_FILE)
    except Exception as exc:  # no speakers, file missing, ...
        log.warning("Could not play the chime: %s", exc)
