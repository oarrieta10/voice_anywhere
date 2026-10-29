"""Record from the default microphone into memory. Nothing is written to disk.

The sound card hands us small blocks of samples on its own thread; we keep them in a
list and join them into one 16 kHz mono float32 numpy array when recording stops.
A recording that reaches the maximum length stops taking audio and calls `on_limit`
(on a separate thread), so the app can transcribe what it has.
For the sound bars, `on_level` gets the loudness of each block (a number from 0 to 1);
only that number is passed on, nothing is kept.
"""
import math
import threading

import numpy as np

SAMPLE_RATE = 16000  # what Whisper expects
DEFAULT_MAX_SECONDS = 120
QUIET_DB, LOUD_DB = -60.0, -18.0  # loudness shown as no bars / full bars


def loudness(block) -> float:
    """How loud a block of samples is, from 0 (silence) to 1 (loud speech).

    Uses the average power in decibels, which follows how loud sound seems to the ear.
    """
    if len(block) == 0:
        return 0.0
    rms = math.sqrt(float(np.mean(np.square(block, dtype=np.float64))))
    db = 20 * math.log10(rms + 1e-9)
    return max(0.0, min(1.0, (db - QUIET_DB) / (LOUD_DB - QUIET_DB)))


class RecorderError(Exception):
    """Raised when the microphone cannot be opened."""


def _default_stream_factory(**kwargs):
    import sounddevice

    return sounddevice.InputStream(**kwargs)


class Recorder:
    def __init__(self, max_seconds=DEFAULT_MAX_SECONDS, on_limit=None, on_level=None,
                 stream_factory=_default_stream_factory):
        self.max_frames = int(max_seconds * SAMPLE_RATE)
        self.on_limit = on_limit
        self.on_level = on_level
        self.peak_level = 0.0  # loudest block of the current recording (for the log)
        self._stream_factory = stream_factory
        self._stream = None
        self._chunks = []
        self._frames = 0
        self._limit_hit = False
        self._lock = threading.Lock()

    @property
    def recording(self) -> bool:
        return self._stream is not None

    def start(self) -> None:
        if self._stream is not None:
            return
        with self._lock:
            self._chunks, self._frames, self._limit_hit = [], 0, False
            self.peak_level = 0.0
        try:
            stream = self._stream_factory(samplerate=SAMPLE_RATE, channels=1,
                                          dtype="float32", callback=self._callback)
            stream.start()
        except Exception as exc:  # no microphone, device busy, ...
            raise RecorderError(f"Could not open the microphone: {exc}"[:300]) from exc
        self._stream = stream

    def _callback(self, indata, frames, time_info, status):
        with self._lock:
            if self._limit_hit:
                return
            room = self.max_frames - self._frames
            block = indata[:room, 0].copy()
            self._chunks.append(block)
            self._frames += len(block)
            self._limit_hit = self._frames >= self.max_frames
            limit_hit = self._limit_hit
        level = loudness(block)
        self.peak_level = max(self.peak_level, level)
        if self.on_level is not None:
            self.on_level(level)
        if limit_hit and self.on_limit is not None:
            # Never stop the stream from inside its own callback.
            threading.Thread(target=self.on_limit, name="recording-limit", daemon=True).start()

    def _close(self) -> None:
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
            finally:
                stream.close()

    def stop(self) -> np.ndarray:
        """Stop recording and return the audio (an empty array if there was none)."""
        self._close()
        with self._lock:
            chunks, self._chunks = self._chunks, []
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(chunks)

    def cancel(self) -> None:
        """Stop recording and throw the audio away."""
        self._close()
        with self._lock:
            self._chunks = []

    @property
    def seconds(self) -> float:
        return self._frames / SAMPLE_RATE
