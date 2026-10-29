"""Start Voice Anywhere:  .venv\\Scripts\\pythonw.exe -m voice_anywhere

Sets up the log file first (under pythonw.exe there is no console, and sys.stdout and
sys.stderr are None, so a stray print would crash the app), then makes sure only one
copy runs, then starts the tray app. Startup problems are shown in a Windows message box.
"""
import ctypes
import logging
import logging.handlers
import os
import sys
from pathlib import Path

MUTEX_NAME = "Local\\VoiceAnywhere.SingleInstance"
ERROR_ALREADY_EXISTS = 183
MB_ICONERROR = 0x10


def log_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    path = Path(base) / "voice-anywhere"
    path.mkdir(parents=True, exist_ok=True)
    return path


def setup_logging() -> Path:
    path = log_dir() / "voice-anywhere.log"
    if sys.stdout is None or sys.stderr is None:
        stream = open(log_dir() / "output.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stdout or stream
        sys.stderr = sys.stderr or stream
    handler = logging.handlers.RotatingFileHandler(path, maxBytes=500_000, backupCount=2,
                                                   encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    logging.getLogger("faster_whisper").setLevel(logging.WARNING)
    return path


def already_running() -> bool:
    """Create a named mutex; if it already exists, another copy is running."""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    # The handle is deliberately never closed: Windows frees it when the process exits.
    globals()["_mutex"] = handle
    return ctypes.get_last_error() == ERROR_ALREADY_EXISTS


def use_sharp_display_scaling() -> None:
    """Tell Windows we handle display scaling (125%, 150%...) ourselves.

    Without this, Windows stretches the pill and the tray icon, which makes them blurry.
    """
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # per monitor v2
    except (AttributeError, OSError):
        pass  # older Windows: it still works, just less sharp


def message_box(text: str) -> None:
    ctypes.windll.user32.MessageBoxW(None, text, "Voice Anywhere", MB_ICONERROR)


def main() -> int:
    log_path = setup_logging()
    log = logging.getLogger("voice_anywhere")
    if already_running():
        log.info("Another copy is already running; exiting")
        return 0
    use_sharp_display_scaling()
    try:
        from .app import run

        return run()
    except SystemExit as exc:
        if exc.code in (None, 0):
            return 0
        log.error("Could not start: %s", exc.code)
        message_box(f"Voice Anywhere could not start.\n\n{exc.code}")
        return 1
    except Exception:
        log.exception("Voice Anywhere crashed")
        message_box(f"Voice Anywhere stopped because of an unexpected error.\n\n"
                    f"Details are in {log_path}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
