"""A short, soft two-note chime when listening starts. Fully offline, no sound file.

The notes are worked out here as numbers and played through the default speakers.
Recording has already begun by then, so the first SKIP_SECONDS of audio are thrown away
(see Recorder) to keep the chime from being transcribed. A chime that cannot play is only
logged: dictation carries on without it.
Settings:
  VOICE_CHIME  "on" (default) or "off"
"""
import logging
import os

import numpy as np

log = logging.getLogger("voice_anywhere")

PLAY_RATE = 44100  # samples per second, a standard rate for speakers
NOTES = (659.25, 880.0)  # E and A, a rising step
NOTE_SECONDS = 0.1
VOLUME = 0.12  # 1.0 is full scale
SECONDS = len(NOTES) * NOTE_SECONDS
SKIP_SECONDS = SECONDS + 0.15  # the speakers start a moment after the microphone


def enabled() -> bool:
    return os.environ.get("VOICE_CHIME", "on").strip().lower() not in ("off", "0", "no", "false")


def make_chime() -> np.ndarray:
    """The chime as float32 samples. Each note fades in and out, so it never clicks."""
    length = int(NOTE_SECONDS * PLAY_RATE)
    t = np.arange(length) / PLAY_RATE
    fade = np.minimum(1.0, t / 0.005) * np.exp(-t * 18) * np.minimum(1.0, (NOTE_SECONDS - t) / 0.01)
    notes = [np.sin(2 * np.pi * pitch * t) * fade for pitch in NOTES]
    return (VOLUME * np.concatenate(notes)).astype(np.float32)


def _default_player(samples, rate):
    import sounddevice

    sounddevice.play(samples, rate)  # returns at once; the sound plays in the background


def play(player=_default_player) -> None:
    try:
        player(make_chime(), PLAY_RATE)
    except Exception as exc:  # no speakers, device busy, ...
        log.warning("Could not play the chime: %s", exc)
