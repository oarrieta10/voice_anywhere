"""Writes the shortcut icons from the tray icon drawing:
  voice_anywhere\\voice-anywhere.ico        black, for the Startup shortcut
  voice_anywhere\\voice-anywhere-white.ico  white, for the desktop shortcut

Run from the project root:  .venv\\Scripts\\python.exe -m scripts.make_icon
"""
from pathlib import Path

from voice_anywhere.tray import STATE_COLOURS, make_icon

folder = Path(__file__).resolve().parent.parent / "voice_anywhere"
for name, colour in (("voice-anywhere.ico", STATE_COLOURS["idle"]),
                     ("voice-anywhere-white.ico", (255, 255, 255))):
    path = folder / name
    make_icon(colour).save(path, sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
    print(f"Wrote {path}")
