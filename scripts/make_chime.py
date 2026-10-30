"""Turns sounds/intuition-561.ogg into sounds/intuition-561.wav, the file the app plays.

Windows' built-in sound player only reads WAV files, so run this again if the chime changes:
    .venv\\Scripts\\python.exe -m scripts.make_chime
"""
import wave
from pathlib import Path

import av
import numpy as np

SOUNDS = Path(__file__).resolve().parent.parent / "sounds"
SOURCE = SOUNDS / "intuition-561.ogg"
TARGET = SOUNDS / "intuition-561.wav"


def main():
    with av.open(str(SOURCE)) as container:
        stream = container.streams.audio[0]
        blocks = [frame.to_ndarray() for frame in container.decode(stream)]
        rate = stream.rate
    samples = np.concatenate(blocks, axis=1).astype(np.float32).mean(axis=0)
    with wave.open(str(TARGET), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)  # 16-bit
        out.setframerate(rate)
        out.writeframes((np.clip(samples, -1, 1) * 32767).astype(np.int16).tobytes())
    print(f"Wrote {TARGET} ({len(samples) / rate:.2f} s)")


if __name__ == "__main__":
    main()
