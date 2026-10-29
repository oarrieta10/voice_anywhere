"""Draws the floating pill: sound bars while listening, a wave of dots while transcribing.

This file only makes pictures (with Pillow); overlay.py puts them on the screen. That
keeps the look testable without any window.

PillAnimator holds the state and is asked for one picture per frame:
  listen()        pill grows and fades in, bars follow set_level()
  think()         pill shrinks to the smaller dots pill, a soft wave runs across the dots
  hide()          pill fades out
  frame(now)      the picture for this moment, or None once fully hidden
Its methods may be called from any thread.
"""
import math
import threading

from PIL import Image, ImageDraw

LISTEN_SIZE = (150, 44)  # pill width, height at 100% display scaling
THINK_SIZE = (110, 34)
MARGIN = 3  # transparent border around the pill, so its soft edge is not cut off
N_BARS, BAR_WIDTH, BAR_GAP_SIDES, BAR_MAX = 16, 4, 22, 27
N_DOTS, DOT_SIZE, DOT_GAP_SIDES = 12, 4, 18
OPACITY = 0.94  # the pill is very slightly see-through
SUPERSAMPLE = 3  # draw larger, then shrink: smooth edges
FADE_SECONDS, MORPH_SECONDS = 0.16, 0.25
ATTACK_SECONDS, RELEASE_SECONDS = 0.05, 0.18  # how fast the bars rise and fall
WAVE_SECONDS = 1.6  # time for the brightness wave to cross the dots

HIDDEN, LISTENING, THINKING = "hidden", "listening", "thinking"


def canvas_size(scale: float = 1.0) -> tuple[int, int]:
    """Size of every picture (the listening pill, which is the largest, plus the margin)."""
    return (round((LISTEN_SIZE[0] + 2 * MARGIN) * scale),
            round((LISTEN_SIZE[1] + 2 * MARGIN) * scale))


def bar_heights(level: float, t: float) -> list[float]:
    """Bar heights (at 100% scaling) for a loudness `level` from 0 (silence) to 1 (loud).

    Middle bars reach higher than the outer ones, and each bar wobbles a little on its own
    so the shape looks alive. In silence every bar shrinks to a round dot.
    """
    heights = []
    for i in range(N_BARS):
        shape = 0.45 + 0.55 * math.sin(math.pi * (i + 0.5) / N_BARS)
        wobble = 0.7 + 0.3 * math.sin(t * (6 + (i * 7) % 5) + i * 2.4)
        amount = min(1.0, level * shape * wobble * 1.15)
        heights.append(BAR_WIDTH + (BAR_MAX - BAR_WIDTH) * amount)
    return heights


def dot_brightness(t: float) -> list[float]:
    """Brightness of each dot (0-1): a soft bright patch moving slowly left to right."""
    values = []
    for i in range(N_DOTS):
        phase = i / N_DOTS - t / WAVE_SECONDS
        peak = max(0.0, math.cos(2 * math.pi * phase)) ** 4
        values.append(0.5 + 0.5 * peak)
    return values


def _lerp(a, b, f):
    return a + (b - a) * f


def _ease(f):
    return f * f * (3 - 2 * f)  # smoothstep: starts and ends gently


def render(level: float, t: float, appear: float = 1.0, morph: float = 0.0,
           scale: float = 1.0) -> Image.Image:
    """One picture of the pill.

    appear: 0 = invisible, 1 = fully shown (it also grows from 85% to full size)
    morph:  0 = listening pill with bars, 1 = thinking pill with dots
    scale:  Windows display scaling (1.0 = 100%, 1.5 = 150%)
    """
    k = scale * SUPERSAMPLE
    cw, ch = canvas_size(scale)
    img = Image.new("RGBA", (cw * SUPERSAMPLE, ch * SUPERSAMPLE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    grow = 0.85 + 0.15 * _ease(appear)
    w = _lerp(LISTEN_SIZE[0], THINK_SIZE[0], _ease(morph)) * grow
    h = _lerp(LISTEN_SIZE[1], THINK_SIZE[1], _ease(morph)) * grow
    # The pill keeps its bottom-right corner in place, so it grows out of the screen corner.
    right, bottom = (LISTEN_SIZE[0] + MARGIN) * k, (LISTEN_SIZE[1] + MARGIN) * k
    left, top = right - w * k, bottom - h * k
    draw.rounded_rectangle((left, top, right, bottom), radius=h * k / 2, fill=(0, 0, 0, 255),
                           outline=(70, 70, 70, 255), width=max(1, round(k)))
    cx, cy = (left + right) / 2, (top + bottom) / 2
    inner = grow * k

    def grey(v):
        g = round(255 * max(0.0, min(1.0, v)))
        return (g, g, g, 255)  # white blended over the black pill

    def bars():
        span = (LISTEN_SIZE[0] - 2 * BAR_GAP_SIDES) * inner
        step = span / (N_BARS - 1)
        colour = grey(1 - _ease(morph))
        for i, bh in enumerate(bar_heights(level, t)):
            x = cx - span / 2 + i * step
            half_w, half_h = BAR_WIDTH * inner / 2, bh * inner / 2
            draw.rounded_rectangle((x - half_w, cy - half_h, x + half_w, cy + half_h),
                                   radius=half_w, fill=colour)

    def dots():
        span = (THINK_SIZE[0] - 2 * DOT_GAP_SIDES) * inner
        step = span / (N_DOTS - 1)
        for i, b in enumerate(dot_brightness(t)):
            x = cx - span / 2 + i * step
            r = DOT_SIZE * inner / 2
            draw.ellipse((x - r, cy - r, x + r, cy + r), fill=grey(b * _ease(morph)))

    # Whichever is fading in is drawn last, on top.
    for layer in ((bars, dots) if morph >= 0.5 else (dots, bars)):
        layer()

    img = img.resize((cw, ch), Image.LANCZOS)
    alpha = OPACITY * _ease(max(0.0, min(1.0, appear)))
    a = img.getchannel("A").point(lambda v: round(v * alpha))
    img.putalpha(a)
    return img


class PillAnimator:
    def __init__(self, scale: float = 1.0):
        self.scale = scale
        self.state = HIDDEN
        self.appear = 0.0
        self.morph = 0.0
        self.level = 0.0  # smoothed loudness used for drawing
        self._target_level = 0.0
        self._last = None
        self._lock = threading.Lock()

    def listen(self) -> None:
        with self._lock:
            if self.state == HIDDEN:
                self.morph = 0.0
            self.state = LISTENING
            self._target_level = 0.0

    def think(self) -> None:
        with self._lock:
            self.state = THINKING

    def hide(self) -> None:
        with self._lock:
            if self.state != HIDDEN:
                self.state = "closing"

    def set_level(self, level: float) -> None:
        """Latest microphone loudness, 0 to 1. Called from the recording thread."""
        self._target_level = level

    @property
    def active(self) -> bool:
        return self.state != HIDDEN

    def frame(self, now: float):
        """The picture for time `now` (seconds), or None when there is nothing to show."""
        with self._lock:
            dt = 0.0 if self._last is None else max(0.0, min(0.1, now - self._last))
            self._last = now
            if self.state == HIDDEN:
                self._last = None
                return None
            showing = self.state in (LISTENING, THINKING)
            step = dt / FADE_SECONDS
            self.appear = min(1.0, self.appear + step) if showing else max(0.0, self.appear - step)
            if self.state == THINKING:
                self.morph = min(1.0, self.morph + dt / MORPH_SECONDS)
            target = self._target_level if self.state == LISTENING else 0.0
            tau = ATTACK_SECONDS if target > self.level else RELEASE_SECONDS
            self.level += (target - self.level) * (1 - math.exp(-dt / tau)) if dt else 0.0
            if not showing and self.appear <= 0.0:
                self.state, self.morph, self.level, self._last = HIDDEN, 0.0, 0.0, None
                return None
            level, appear, morph = self.level, self.appear, self.morph
        return render(level, now, appear, morph, self.scale)
