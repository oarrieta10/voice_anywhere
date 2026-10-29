import io
from types import SimpleNamespace

import numpy as np
import pytest

from voice_anywhere import transcriber


class FakeModel:
    def __init__(self, texts=(" Hello", " world. ")):
        self.texts = texts
        self.calls = []

    def transcribe(self, source, **kwargs):
        self.calls.append((source, kwargs))
        segments = [SimpleNamespace(text=t) for t in self.texts]
        return iter(segments), SimpleNamespace(language="en", duration=2.04)


@pytest.fixture
def fake_model(monkeypatch):
    model = FakeModel()
    monkeypatch.setattr(transcriber, "_get_model", lambda: model)
    return model


def test_array_is_passed_straight_to_the_model(fake_model):
    audio = np.zeros(16000, dtype=np.float32)
    result = transcriber.transcribe(audio)
    assert result["text"] == "Hello world."
    assert result["audio_seconds"] == 2.0
    source, kwargs = fake_model.calls[0]
    assert source is audio
    assert kwargs["vad_filter"] is True


def test_bytes_are_wrapped_in_a_file_like_object(fake_model):
    transcriber.transcribe(b"RIFF....")
    source, _ = fake_model.calls[0]
    assert isinstance(source, io.BytesIO)
    assert source.getvalue() == b"RIFF...."


@pytest.mark.parametrize("empty", [b"", None, np.zeros(0, dtype=np.float32)])
def test_empty_audio_is_rejected(fake_model, empty):
    with pytest.raises(transcriber.TranscriberError):
        transcriber.transcribe(empty)
    assert fake_model.calls == []


def test_model_errors_become_transcriber_errors(monkeypatch):
    class Broken:
        def transcribe(self, *a, **k):
            raise RuntimeError("bad audio")

    monkeypatch.setattr(transcriber, "_get_model", lambda: Broken())
    with pytest.raises(transcriber.TranscriberError, match="bad audio"):
        transcriber.transcribe(np.ones(10, dtype=np.float32))


def test_language_setting(monkeypatch):
    monkeypatch.setenv("VOICE_WHISPER_LANG", "auto")
    assert transcriber.language() is None and transcriber.allowed_languages() is None
    monkeypatch.setenv("VOICE_WHISPER_LANG", "ES")
    assert transcriber.language() == "es" and transcriber.allowed_languages() is None
    monkeypatch.setenv("VOICE_WHISPER_LANG", "en, es")
    assert transcriber.language() is None
    assert transcriber.allowed_languages() == ["en", "es"]


class GuessingModel:
    """Fake model that 'detects' a given language when none is forced."""

    def __init__(self, guess, probs):
        self.guess, self.probs = guess, probs
        self.languages_asked = []

    def transcribe(self, source, language=None, **kwargs):
        self.languages_asked.append(language)
        lang = language or self.guess
        info = SimpleNamespace(language=lang, duration=1.0,
                               all_language_probs=None if language else self.probs)
        return iter([SimpleNamespace(text=f" text in {lang}")]), info


def test_detected_allowed_language_is_used_directly(monkeypatch):
    monkeypatch.setenv("VOICE_WHISPER_LANG", "en,es")
    model = GuessingModel("es", [("es", 0.9), ("en", 0.05)])
    monkeypatch.setattr(transcriber, "_get_model", lambda: model)
    result = transcriber.transcribe(np.zeros(16000, dtype=np.float32))
    assert result["language"] == "es" and result["text"] == "text in es"
    assert model.languages_asked == [None]  # one pass, no extra work


def test_other_language_guess_falls_back_to_best_allowed(monkeypatch):
    monkeypatch.setenv("VOICE_WHISPER_LANG", "en,es")
    model = GuessingModel("pt", [("pt", 0.55), ("es", 0.35), ("gl", 0.05), ("en", 0.02)])
    monkeypatch.setattr(transcriber, "_get_model", lambda: model)
    result = transcriber.transcribe(np.zeros(16000, dtype=np.float32))
    assert result["language"] == "es" and result["text"] == "text in es"
    assert model.languages_asked == [None, "es"]


def test_bytes_can_be_read_twice_when_redoing(monkeypatch):
    monkeypatch.setenv("VOICE_WHISPER_LANG", "en,es")
    seen = []

    class Model(GuessingModel):
        def transcribe(self, source, language=None, **kwargs):
            seen.append(source.read())
            return super().transcribe(source, language, **kwargs)

    monkeypatch.setattr(transcriber, "_get_model", lambda: Model("it", [("it", 0.6), ("en", 0.3)]))
    transcriber.transcribe(b"RIFF....")
    assert seen == [b"RIFF....", b"RIFF...."]
