import threading

import numpy as np
import pytest

from voice_anywhere.recorder import SAMPLE_RATE, Recorder, RecorderError, loudness


class FakeStream:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.started = self.stopped = self.closed = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def close(self):
        self.closed = True

    def feed(self, values):
        block = np.asarray(values, dtype=np.float32).reshape(-1, 1)
        self.kwargs["callback"](block, len(block), None, None)


@pytest.fixture
def streams():
    made = []

    def factory(**kwargs):
        made.append(FakeStream(**kwargs))
        return made[-1]

    return made, factory


def test_records_16khz_mono_and_joins_blocks(streams):
    made, factory = streams
    rec = Recorder(stream_factory=factory)
    rec.start()
    stream = made[0]
    assert stream.started and rec.recording
    assert stream.kwargs["samplerate"] == SAMPLE_RATE
    assert stream.kwargs["channels"] == 1
    assert stream.kwargs["dtype"] == "float32"
    stream.feed([0.1, 0.2])
    stream.feed([0.3])
    audio = rec.stop()
    assert audio.dtype == np.float32
    np.testing.assert_allclose(audio, [0.1, 0.2, 0.3])
    assert stream.stopped and stream.closed and not rec.recording


def test_stop_without_audio_returns_empty_array(streams):
    _, factory = streams
    rec = Recorder(stream_factory=factory)
    rec.start()
    assert len(rec.stop()) == 0


def test_cancel_discards_audio(streams):
    made, factory = streams
    rec = Recorder(stream_factory=factory)
    rec.start()
    made[0].feed([0.5] * 10)
    rec.cancel()
    assert made[0].closed and not rec.recording
    assert len(rec.stop()) == 0


def test_next_recording_starts_fresh(streams):
    made, factory = streams
    rec = Recorder(stream_factory=factory)
    rec.start()
    made[0].feed([1.0])
    rec.stop()
    rec.start()
    made[1].feed([2.0])
    np.testing.assert_allclose(rec.stop(), [2.0])


def test_maximum_length_trims_and_calls_on_limit(streams):
    made, factory = streams
    called = threading.Event()
    rec = Recorder(max_seconds=4 / SAMPLE_RATE, on_limit=called.set, stream_factory=factory)
    rec.start()
    made[0].feed([1, 2, 3])
    assert not called.is_set()
    made[0].feed([4, 5, 6])
    made[0].feed([7])  # ignored once the limit is reached
    assert called.wait(2)
    np.testing.assert_allclose(rec.stop(), [1, 2, 3, 4])


def test_first_moments_are_skipped_on_every_recording(streams):
    made, factory = streams
    rec = Recorder(skip_seconds=lambda: 3 / SAMPLE_RATE, stream_factory=factory)
    rec.start()
    made[0].feed([1, 2])
    made[0].feed([3, 4, 5])
    np.testing.assert_allclose(rec.stop(), [4, 5])
    rec.start()
    made[1].feed([6, 7, 8, 9])
    np.testing.assert_allclose(rec.stop(), [9])


def test_skipped_audio_does_not_count_towards_the_limit(streams):
    made, factory = streams
    rec = Recorder(max_seconds=2 / SAMPLE_RATE, skip_seconds=lambda: 2 / SAMPLE_RATE,
                   stream_factory=factory)
    rec.start()
    made[0].feed([1, 2, 3, 4, 5])
    np.testing.assert_allclose(rec.stop(), [3, 4])


def test_ready_is_called_once_when_the_first_sound_arrives(streams):
    made, factory = streams
    ready = threading.Semaphore(0)
    rec = Recorder(on_ready=ready.release, ready_timeout=60, stream_factory=factory)
    rec.start()
    assert not ready.acquire(timeout=0.05)  # the microphone is open but not hearing yet
    made[0].feed([0.1])
    assert ready.acquire(timeout=2)
    made[0].feed([0.2])
    assert not ready.acquire(timeout=0.05)
    rec.stop()


def test_ready_is_called_anyway_if_no_sound_ever_comes(streams):
    _, factory = streams
    ready = threading.Event()
    rec = Recorder(on_ready=ready.set, ready_timeout=0.01, stream_factory=factory)
    rec.start()
    assert ready.wait(2)
    rec.stop()


def test_ready_is_not_called_after_stopping(streams):
    _, factory = streams
    ready = threading.Event()
    rec = Recorder(on_ready=ready.set, ready_timeout=0.05, stream_factory=factory)
    rec.start()
    rec.cancel()
    assert not ready.wait(0.2)


def test_loudness_of_each_block_is_reported(streams):
    made, factory = streams
    levels = []
    rec = Recorder(on_level=levels.append, stream_factory=factory)
    rec.start()
    made[0].feed([0.0] * 160)  # silence
    made[0].feed([0.3, -0.3] * 80)  # speech-like loudness
    rec.stop()
    assert levels[0] == 0.0
    assert levels[1] == 1.0


def test_loudness_scale():
    assert loudness(np.zeros(100, dtype=np.float32)) == 0.0
    assert loudness(np.zeros(0, dtype=np.float32)) == 0.0
    quiet = loudness(np.full(100, 0.003, dtype=np.float32))  # about -50 dB
    medium = loudness(np.full(100, 0.03, dtype=np.float32))  # about -30 dB
    assert 0.0 < quiet < medium < 1.0


def test_microphone_failure_raises_recorder_error():
    def broken(**kwargs):
        raise OSError("no device")

    rec = Recorder(stream_factory=broken)
    with pytest.raises(RecorderError, match="no device"):
        rec.start()
    assert not rec.recording
