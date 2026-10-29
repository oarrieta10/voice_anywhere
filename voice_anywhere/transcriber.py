"""Local speech-to-text with faster-whisper. Audio never leaves this computer.

The model is loaded once (in the background at startup, or on first use) and
reused. Only already-downloaded models are used (local_files_only), so nothing
is fetched from the internet. Settings:
  VOICE_WHISPER_MODEL  model size or local path   (default "small")
  VOICE_WHISPER_LANG   language code, "auto" to detect (default "en")
"""
import io
import os
import threading
import time

DEFAULT_MODEL = "small"

_model = None
_load_error = None
_lock = threading.Lock()


class TranscriberError(Exception):
    """Raised when dictation cannot be transcribed."""


def model_name() -> str:
    return os.environ.get("VOICE_WHISPER_MODEL", DEFAULT_MODEL)


def language() -> str | None:
    lang = os.environ.get("VOICE_WHISPER_LANG", "en").strip().lower()
    return None if lang in ("", "auto") else lang


def available() -> bool:
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return False
    return True


def status() -> dict:
    return {"available": available(), "model": model_name(),
            "loaded": _model is not None, "error": _load_error}


def _get_model():
    global _model, _load_error
    with _lock:
        if _model is None:
            try:
                from faster_whisper import WhisperModel

                _model = WhisperModel(model_name(), device="cpu", compute_type="int8",
                                      local_files_only=True)
                _load_error = None
            except ImportError as exc:
                _load_error = "faster-whisper is not installed in this project's .venv"
                raise TranscriberError(_load_error) from exc
            except Exception as exc:  # model missing from the local cache, bad path, ...
                _load_error = f"Could not load Whisper model '{model_name()}': {exc}"[:300]
                raise TranscriberError(_load_error) from exc
        return _model


def preload() -> None:
    """Warm the model in a background thread so the first dictation is quick."""
    if not available():
        return

    def _warm():
        try:
            _get_model()
        except TranscriberError:
            pass  # reported via status() and on first use

    threading.Thread(target=_warm, name="whisper-preload", daemon=True).start()


def transcribe(audio) -> dict:
    """Return {"text", "language", "audio_seconds", "elapsed_seconds"}.

    `audio` is either the bytes of an audio file (any format PyAV can decode) or
    a 16 kHz mono float32 numpy array, as recorded by recorder.py.
    """
    if audio is None or len(audio) == 0:
        raise TranscriberError("No audio received")
    source = io.BytesIO(audio) if isinstance(audio, (bytes, bytearray)) else audio
    model = _get_model()
    started = time.perf_counter()
    try:
        segments, info = model.transcribe(source, language=language(),
                                          vad_filter=True, beam_size=5)
        text = " ".join(s.text.strip() for s in segments).strip()
    except Exception as exc:  # undecodable audio, etc.
        raise TranscriberError(f"Could not transcribe the recording: {exc}"[:300]) from exc
    return {"text": text, "language": info.language,
            "audio_seconds": round(info.duration, 1),
            "elapsed_seconds": round(time.perf_counter() - started, 1)}
