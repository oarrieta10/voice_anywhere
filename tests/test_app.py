import uuid

import numpy as np
import pytest

from voice_anywhere import __main__ as main_module
from voice_anywhere.app import IDLE, LISTENING, TRANSCRIBING, Dictation
from voice_anywhere.recorder import SAMPLE_RATE, RecorderError


class FakeRecorder:
    def __init__(self, seconds=2.0, fail=False):
        self.seconds = seconds
        self.fail = fail
        self.log = []

    def start(self):
        if self.fail:
            raise RecorderError("Could not open the microphone: no device")
        self.log.append("start")

    def stop(self):
        self.log.append("stop")
        return np.zeros(int(self.seconds * SAMPLE_RATE), dtype=np.float32)

    def cancel(self):
        self.log.append("cancel")


class FakeInserter:
    def __init__(self):
        self.log = []

    def remember_target(self):
        self.log.append("remember")

    def insert(self, text):
        self.log.append(("insert", text))
        return True


class FakeUI:
    def __init__(self):
        self.states = []
        self.notes = []

    def set_state(self, state):
        self.states.append(state)

    def notify(self, message, kind="error"):
        self.notes.append((kind, message))


class FakeHotkey:
    def __init__(self):
        self.log = []

    def enable_cancel(self):
        self.log.append("esc on")

    def disable_cancel(self):
        self.log.append("esc off")


def make(text="Hello world.", transcribe=None, **recorder_kwargs):
    pending = []
    recorder, inserter, ui, hotkey = FakeRecorder(**recorder_kwargs), FakeInserter(), FakeUI(), FakeHotkey()

    def fake_transcribe(audio):
        return {"text": text, "language": "en", "audio_seconds": len(audio) / SAMPLE_RATE,
                "elapsed_seconds": 0.5}

    d = Dictation(recorder, inserter, transcribe or fake_transcribe, ui, spawn=pending.append)
    d.hotkey = hotkey
    d.press_only = d.toggle

    def press_and_mic_answers():
        d.press_only()
        d.mic_ready()

    d.toggle = press_and_mic_answers
    return d, recorder, inserter, ui, hotkey, pending


def test_chime_sounds_once_when_listening_starts():
    d, *_ = make()
    chimes = []
    d.chime = lambda: chimes.append(d.state)
    d.toggle()
    assert chimes == [LISTENING]
    d.toggle()
    assert chimes == [LISTENING]


def test_pill_and_chime_wait_for_the_microphone():
    d, recorder, inserter, ui, hotkey, pending = make()
    chimes = []
    d.chime = lambda: chimes.append(ui.states[-1])
    d.press_only()
    assert d.state == LISTENING and recorder.log == ["start"]
    assert ui.states == [] and chimes == []
    d.mic_ready()
    assert ui.states == [LISTENING] and chimes == [LISTENING]
    d.mic_ready()
    assert ui.states == [LISTENING] and chimes == [LISTENING]


def test_stopping_before_the_microphone_answers_shows_nothing_late():
    d, recorder, inserter, ui, hotkey, pending = make(seconds=0.1)
    chimes = []
    d.chime = lambda: chimes.append(True)
    d.press_only()
    d.press_only()
    d.mic_ready()
    assert d.state == IDLE and chimes == [] and LISTENING not in ui.states


def test_no_chime_when_the_microphone_fails():
    d, *_ = make(fail=True)
    chimes = []
    d.chime = lambda: chimes.append(d.state)
    d.toggle()
    assert chimes == []


def test_press_speak_press_inserts_text():
    d, recorder, inserter, ui, hotkey, pending = make()
    d.toggle()
    assert d.state == LISTENING
    assert inserter.log == ["remember"] and recorder.log == ["start"]
    d.toggle()
    assert d.state == TRANSCRIBING
    d.toggle()  # pressing again while transcribing is ignored
    assert recorder.log == ["start", "stop"]
    pending.pop()()  # run the background job
    assert inserter.log == ["remember", ("insert", "Hello world.")]
    assert ui.states == [LISTENING, TRANSCRIBING, IDLE]
    assert hotkey.log == ["esc on", "esc off"]


def test_escape_cancels_and_inserts_nothing():
    d, recorder, inserter, ui, hotkey, pending = make()
    d.toggle()
    d.cancel()
    assert d.state == IDLE
    assert recorder.log == ["start", "cancel"]
    assert pending == [] and inserter.log == ["remember"]
    assert hotkey.log == ["esc on", "esc off"]


def test_escape_when_idle_does_nothing():
    d, recorder, *_ = make()
    d.cancel()
    assert recorder.log == [] and d.state == IDLE


def test_very_short_recording_is_ignored():
    d, recorder, inserter, ui, hotkey, pending = make(seconds=0.1)
    d.toggle()
    d.toggle()
    assert d.state == IDLE and pending == []


def test_maximum_length_transcribes():
    d, recorder, inserter, ui, hotkey, pending = make()
    d.toggle()
    d.limit_reached()
    assert d.state == TRANSCRIBING
    pending.pop()()
    assert ("insert", "Hello world.") in inserter.log


def test_no_speech_shows_message_and_inserts_nothing():
    d, recorder, inserter, ui, hotkey, pending = make(text="")
    d.toggle()
    d.toggle()
    pending.pop()()
    assert ui.notes == [("info", "No speech heard")]
    assert inserter.log == ["remember"] and d.state == IDLE


def test_microphone_error_is_shown_and_stays_idle():
    d, recorder, inserter, ui, hotkey, pending = make(fail=True)
    d.toggle()
    assert d.state == IDLE and hotkey.log == []
    assert ui.notes[0][0] == "error" and "microphone" in ui.notes[0][1]


def test_transcription_error_is_shown_and_returns_to_idle():
    def broken(audio):
        raise RuntimeError("model missing")

    d, recorder, inserter, ui, hotkey, pending = make(transcribe=broken)
    d.toggle()
    d.toggle()
    pending.pop()()
    assert ui.notes == [("error", "model missing")]
    assert d.state == IDLE


def test_text_is_cleaned_before_pasting(monkeypatch):
    monkeypatch.delenv("VOICE_CLEANUP", raising=False)
    d, recorder, inserter, ui, hotkey, pending = make(text="Um, the the pump is on.")
    d.toggle()
    d.toggle()
    pending.pop()()
    assert inserter.log[-1] == ("insert", "The pump is on.")


def test_cleanup_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("VOICE_CLEANUP", "off")
    d, recorder, inserter, ui, hotkey, pending = make(text="Um, the pump is on.")
    d.toggle()
    d.toggle()
    pending.pop()()
    assert inserter.log[-1] == ("insert", "Um, the pump is on.")


def test_only_fillers_counts_as_no_speech():
    d, recorder, inserter, ui, hotkey, pending = make(text="Um.")
    d.toggle()
    d.toggle()
    pending.pop()()
    assert ui.notes == [("info", "No speech heard")]
    assert inserter.log == ["remember"]


def test_transcribed_text_is_never_logged(caplog):
    caplog.set_level("DEBUG")
    d, *_, pending = make(text="secret project budget")
    d.toggle()
    d.toggle()
    pending.pop()()
    assert "secret" not in caplog.text
    assert "21 characters" in caplog.text


def test_single_instance_mutex(monkeypatch):
    monkeypatch.setattr(main_module, "MUTEX_NAME", f"Local\\VoiceAnywhereTest.{uuid.uuid4()}")
    assert main_module.already_running() is False
    first = main_module._mutex
    assert main_module.already_running() is True
    main_module._mutex = first  # keep the first handle referenced until the test ends
