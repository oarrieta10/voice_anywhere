# Voice Anywhere: offline dictation for any Windows program

## Purpose
A personal, local-only tray app for one user (Oscar, a consulting engineer). He presses a hotkey
in any program (Outlook, Teams, Word, a browser...), speaks, presses it again, and the words appear
where his cursor is. Speech is turned into text on his own Windows laptop with faster-whisper.
**Audio and text never leave the computer. There is no AI or network call at all.**
`README.md` is the user guide; this file is the guide for working on the code.

The transcription code started as a copy of `app/transcriber.py` from the sibling project
`C:\Tool Dev\eisenhower-organizer` (Kuadrant). The two projects are independent: do not import from,
change or depend on Kuadrant.

## Agreed design
- **Tray app** (`pystray` + `Pillow`) that starts with Windows and lives by the clock. Menu: status, Language (English / Spanish /
  detect English or Spanish, remembered in `%LOCALAPPDATA%\voice-anywhere\settings.json`), Shortcut, Chime, Quit.
- **Hotkey: press once to start, press again to stop** (toggle, not hold-to-talk). Default `Ctrl+Alt+Space`.
  `Esc` while recording cancels and inserts nothing. Register the hotkey with the Win32 `RegisterHotKey`
  function through `ctypes` (no extra package). The tray's Shortcut menu offers F9, Caps Lock and
  Ctrl+Shift, remembered in `settings.json`. Caps Lock and a Ctrl+Shift tap cannot work through
  `RegisterHotKey`, so they use a `WH_KEYBOARD_LL` keyboard hook, installed only while one is chosen.
  The hook must never store or log keys.
- **Recording** from the default microphone with `sounddevice`, 16 kHz mono, kept in memory only
  (never written to disk). A maximum length stops runaway recordings.
- **Feedback:** a small floating black pill in the bottom-right corner above the taskbar (live sound
  bars while listening, a calm dot wave while transcribing, fades in and out), plus
  the tray icon changing state. It must not take keyboard focus away from the target window.
  The pill and a chime (`voice_anywhere/chime.py`, `sounds/intuition-561.wav`, played with the
  standard library's `winsound`) appear together when the microphone delivers its first sound:
  a Bluetooth headset takes about 0.8 s to switch into call mode, and sound cannot play during
  that switch. The sound heard during the chime is thrown away so it is not transcribed. The
  tray's Chime item turns it on or off (remembered in `settings.json`).
- **Transcription:** `voice_anywhere/transcriber.py`, faster-whisper on the CPU, `int8`, `vad_filter=True`,
  `local_files_only=True`. The model is preloaded in the background at start-up.
- **Inserting the text:** save the clipboard, put the text on it, send `Ctrl+V` with the Win32
  `SendInput` function through `ctypes`, then restore the previous clipboard contents.
  Insert into the window that had focus when recording started.
- **Single instance:** a named mutex so a second launch exits quietly.

## Stack
- Python 3, Windows 11, VS Code, PowerShell. Always use `.venv\Scripts\python.exe` directly
  (avoids PowerShell's script-execution policy). The tray app runs under `pythonw.exe` (no console).
- `faster-whisper` (with `av` pinned below 17, see `requirements.txt`), `sounddevice`, `pystray`, `Pillow`.
- Windows calls (hotkey, keyboard input, clipboard, mutex) go through `ctypes`, not extra packages.
- Tests: pytest. Tests never use the microphone, a real hotkey, the real clipboard or a real Whisper model:
  use fakes.

## Commands (run from the project root)
- Install: `python -m venv .venv` then `.venv\Scripts\python.exe -m pip install -r requirements.txt`
- Run (with console, for development): `.venv\Scripts\python.exe -m voice_anywhere`
- Run (no console, what Oscar uses): `.venv\Scripts\pythonw.exe -m voice_anywhere`
- Test: `.venv\Scripts\python.exe -m pip install pytest` once, then `.venv\Scripts\python.exe -m pytest -q`
- There is no linter, formatter or type checker configured. Match the style of the surrounding code.

## Configuration (environment variables)
| Variable | Purpose | Default |
|---|---|---|
| `VOICE_WHISPER_MODEL` | Whisper model size or folder | `small` |
| `VOICE_WHISPER_LANG` | Language code, `auto`, or a list such as `en,es` (detect, choosing only from those) | `en` |
| `VOICE_HOTKEY` | Hotkey, for example `ctrl+alt+space`; the tray's Shortcut menu wins | `ctrl+alt+space` |
| `VOICE_CLEANUP` | Rule-based text cleanup (`voice_anywhere/cleanup.py`), `on` or `off` | `on` |
| `VOICE_CHIME` | Chime when listening starts, `on` or `off`; the tray's Chime item wins | `on` |

## Conventions
- **Plain language.** Oscar is a consulting engineer, not a full-time developer. Explain changes simply
  and spell out acronyms on first use.
- **Privacy:** dictated text can come from real work. Never log the transcribed text or keep audio files.
  Logs may record lengths and timings only.
- Under `pythonw.exe`, `sys.stdout`/`sys.stderr` are `None`: redirect them to a log file in
  `%LOCALAPPDATA%\voice-anywhere\` before anything prints. Show errors to Oscar with a Windows message box
  or a tray notification.
- The Whisper model must already be in the local Hugging Face cache (`small` and `base` are). The app never downloads it.
- Keep the hotkey, recording, transcription and text insertion in separate modules so each can be tested
  with fakes.

## Working with Claude on this project
- Plan first for anything beyond a small fix, and make one change at a time.
- Commit after each working step so any change can be undone.
- Run `pytest -q` after every change and report the result.
- Do not add dependencies beyond those listed above without asking first.
- Do not touch `.venv/`, `__pycache__/`, `.pytest_cache/` or `.git/`.
- At the end of a task, summarise which files changed and why.
