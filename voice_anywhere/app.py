"""Ties the pieces together: hotkey -> recorder -> transcriber -> inserter.

Dictation is the controller. It only talks to the other parts through the objects it is
given, so tests drive it with fakes. run() builds the real parts and starts the app.

States: idle -> listening (hotkey) -> transcribing (hotkey again, or the maximum length)
-> idle. Esc while listening goes straight back to idle and inserts nothing.
The transcribed text is never logged; only lengths and timings are.
"""
import logging
import threading

from . import cleanup, transcriber
from .hotkey import HotkeyListener
from .inserter import Inserter
from .recorder import SAMPLE_RATE, Recorder

log = logging.getLogger("voice_anywhere")

IDLE, LISTENING, TRANSCRIBING = "idle", "listening", "transcribing"
MIN_SECONDS = 0.3  # shorter recordings are treated as an accidental double press


def _clean(text):
    return cleanup.clean(text) if cleanup.enabled() else text


def _spawn(target):
    threading.Thread(target=target, name="dictation", daemon=True).start()


class Dictation:
    def __init__(self, recorder, inserter, transcribe, ui, spawn=_spawn, clean=None):
        """ui needs set_state(state) and notify(message, kind); clean tidies the text."""
        self.clean = clean or _clean
        self.recorder = recorder
        self.inserter = inserter
        self.transcribe = transcribe
        self.ui = ui
        self.spawn = spawn
        self.hotkey = None  # set by run(); needs enable_cancel() and disable_cancel()
        self.state = IDLE
        self._lock = threading.Lock()

    def _set_state(self, state):
        self.state = state
        self.ui.set_state(state)

    def _cancel_key(self, on):
        if self.hotkey is not None:
            (self.hotkey.enable_cancel if on else self.hotkey.disable_cancel)()

    def toggle(self) -> None:
        """Hotkey pressed: start listening, or stop and transcribe."""
        with self._lock:
            if self.state == IDLE:
                self._start()
            elif self.state == LISTENING:
                self._finish()
            # while transcribing, extra presses are ignored

    def cancel(self) -> None:
        """Esc pressed while listening: throw the recording away."""
        with self._lock:
            if self.state != LISTENING:
                return
            self.recorder.cancel()
            self._cancel_key(False)
            log.info("Recording cancelled")
            self._set_state(IDLE)

    def limit_reached(self) -> None:
        """The recorder hit its maximum length: transcribe what we have."""
        with self._lock:
            if self.state == LISTENING:
                log.info("Maximum recording length reached")
                self._finish()

    def _start(self):
        self.inserter.remember_target()
        try:
            self.recorder.start()
        except Exception as exc:
            log.warning("Could not start recording: %s", exc)
            self.ui.notify(str(exc), "error")
            return
        self._cancel_key(True)
        self._set_state(LISTENING)

    def _finish(self):
        audio = self.recorder.stop()
        self._cancel_key(False)
        seconds = len(audio) / SAMPLE_RATE
        log.info("Recorded %.1f s, loudest moment %.2f (0 = silent, 1 = full bars)",
                 seconds, getattr(self.recorder, "peak_level", 0.0))
        if seconds < MIN_SECONDS:
            log.info("Recording too short (%.2f s), nothing to do", seconds)
            self._set_state(IDLE)
            return
        self._set_state(TRANSCRIBING)
        self.spawn(lambda: self._transcribe_and_insert(audio))

    def _transcribe_and_insert(self, audio):
        try:
            result = self.transcribe(audio)
            raw = result["text"]
            text = self.clean(raw)
            log.info("Transcribed %.1f s of audio in %.1f s: %d characters (%d after cleanup)",
                     result["audio_seconds"], result["elapsed_seconds"], len(raw), len(text))
            if text:
                self.inserter.insert(text)
            else:
                self.ui.notify("No speech heard", "info")
        except Exception as exc:
            log.warning("Dictation failed: %s", exc)  # error messages never contain the text
            self.ui.notify(str(exc), "error")
        finally:
            with self._lock:
                self._set_state(IDLE)


def run() -> int:
    """Start the tray app. Returns the process exit code."""
    from .overlay import Overlay
    from .tray import Tray

    overlay = Overlay()
    tray = Tray(overlay)
    recorder = Recorder(on_limit=lambda: dictation.limit_reached(), on_level=overlay.set_level)
    dictation = Dictation(recorder, Inserter(), transcriber.transcribe, tray)
    try:
        listener = HotkeyListener(on_toggle=dictation.toggle, on_cancel=dictation.cancel)
        listener.start()
    except Exception as exc:
        raise SystemExit(str(exc))
    dictation.hotkey = listener
    tray.hotkey_name = listener.hotkey

    def quit_app():
        listener.stop()
        recorder.cancel()
        overlay.stop()

    tray.on_quit = quit_app
    overlay.start()
    transcriber.preload()
    log.info("Voice Anywhere started (hotkey %s, model %s)", listener.hotkey,
             transcriber.model_name())
    tray.run()
    log.info("Voice Anywhere stopped")
    return 0