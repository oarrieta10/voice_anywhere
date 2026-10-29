"""Writes voice_anywhere\\voice-anywhere.ico (used by the shortcut) from the tray icon drawing.

Run from the project root:  .venv\\Scripts\\python.exe -m scripts.make_icon
"""
from pathlib import Path

from voice_anywhere.tray import STATE_COLOURS, make_icon

path = Path(__file__).resolve().parent.parent / "voice_anywhere" / "voice-anywhere.ico"
make_icon(STATE_COLOURS["idle"]).save(path, sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
print(f"Wrote {path}")
