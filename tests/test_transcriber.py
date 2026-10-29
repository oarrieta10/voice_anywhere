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
    assert transcriber.language() is None
    monkeypatch.setenv("VOICE_WHISPER_LANG", "ES")
    assert transcriber.language() == "es"
