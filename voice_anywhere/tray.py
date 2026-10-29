"""Tray icon by the clock (pystray) plus the floating badge.

Tray is the "ui" the Dictation controller talks to. Its methods may be called from any
thread: badge changes are queued and carried out on the tkinter thread, because tkinter
only works from the thread that created it.
"""
import logging
import queue

from PIL import Image, ImageDraw

from . import transcriber

log = logging.getLogger("voice_anywhere")

STATE_COLOURS = {"idle": (52, 101, 164), "listening": (192, 57, 43),
                 "transcribing": (183, 121, 31)}
STATE_TEXT = {"listening": "Listening…  (press the hotkey to stop, Esc to cancel)",
              "transcribing": "Transcribing…"}
BADGE_TEXT = {"listening": "● Listening…", "transcribing": "Transcribing…"}
INFO_SECONDS = 1.5


def make_icon(colour) -> Image.Image:
    """A round icon with a simple white microphone."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((2, 2, size - 2, size - 2), fill=colour)
    white = (255, 255, 255)
    d.rounded_rectangle((24, 12, 40, 38), radius=8, fill=white)  # microphone head
    d.arc((17, 22, 47, 46), start=0, end=180, fill=white, width=4)  # holder
    d.line((32, 46, 32, 52), fill=white, width=4)  # stand
    d.line((23, 53, 41, 53), fill=white, width=4)  # base
    return img


class Tray:
    def __init__(self, root, badge):
        self.root = root
        self.badge = badge
        self.hotkey_name = ""
        self.on_quit = None
        self.state = "idle"
        self._images = {s: make_icon(c) for s, c in STATE_COLOURS.items()}
        self._jobs = queue.Queue()
        self._hide_after = None
        self.icon = None

    # --- called from any thread ---

    def set_state(self, state) -> None:
        self.state = state
        if self.icon is not None:
            self.icon.icon = self._images[state]
            self.icon.title = self._title()
            self.icon.update_menu()
        self._jobs.put(("state", state))

    def notify(self, message, kind="error") -> None:
        if kind == "error":
            log.info("Showing an error notification")
            if self.icon is not None:
                self.icon.notify(message[:250], "Voice Anywhere")
        else:
            self._jobs.put(("info", message))

    # --- tray icon ---

    def status_text(self) -> str:
        if self.state in STATE_TEXT:
            return STATE_TEXT[self.state]
        info = transcriber.status()
        if info["error"]:
            return "Problem: " + info["error"]
        if not info["loaded"]:
            return f"Loading speech model ({info['model']})…"
        return f"Ready: press {self.hotkey_name.title()} to dictate"

    def _title(self) -> str:
        return ("Voice Anywhere: " + self.status_text())[:127]  # Windows tooltip limit

    def start(self) -> None:
        import pystray

        menu = pystray.Menu(
            pystray.MenuItem(lambda item: self.status_text(), None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._quit),
        )
        self.icon = pystray.Icon("voice-anywhere", self._images["idle"], self._title(), menu)
        self.icon.run_detached()
        self.root.after(50, self._poll)
        self.root.after(1000, self._refresh_title)

    def _refresh_title(self) -> None:
        # Picks up "model loaded" (or a loading problem) once the background preload ends.
        if self.icon is not None and self.state == "idle":
            self.icon.title = self._title()
            self.icon.update_menu()
        self.root.after(2000, self._refresh_title)

    def _quit(self, icon=None, item=None) -> None:
        self._jobs.put(("quit", None))

    def stop(self) -> None:
        if self.icon is not None:
            self.icon.stop()

    # --- tkinter thread ---

    def _poll(self) -> None:
        while True:
            try:
                job, value = self._jobs.get_nowait()
            except queue.Empty:
                break
            if job == "state":
                if value in BADGE_TEXT:
                    self._cancel_hide()
                    self.badge.show(BADGE_TEXT[value], value)
                elif self._hide_after is None:  # leave a short message up until its timer ends
                    self.badge.hide()
            elif job == "info":
                self._cancel_hide()
                self.badge.show(value, "info")
                self._hide_after = self.root.after(int(INFO_SECONDS * 1000), self._timed_hide)
            elif job == "quit" and self.on_quit is not None:
                self.on_quit()
                return
        self.root.after(50, self._poll)

    def _timed_hide(self) -> None:
        self._hide_after = None
        if self.state not in BADGE_TEXT:
            self.badge.hide()

    def _cancel_hide(self) -> None:
        if self._hide_after is not None:
            self.root.after_cancel(self._hide_after)
            self._hide_after = None
