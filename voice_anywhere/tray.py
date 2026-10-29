"""Tray icon by the clock (pystray), plus the floating pill (overlay.py).

Tray is the "ui" the Dictation controller talks to. Its methods may be called from any
thread. run() shows the tray icon and blocks until Quit is chosen.
"""
import logging
import threading

from PIL import Image, ImageDraw

from . import settings, transcriber

log = logging.getLogger("voice_anywhere")

# The tray's Language menu: (menu text, VOICE_WHISPER_LANG-style setting).
LANGUAGES = [("English", "en"), ("Spanish", "es"), ("Detect English or Spanish", "en,es")]
LANGUAGE_SHORT = {"en": "English", "es": "Spanish", "en,es": "English or Spanish",
                  "auto": "any language"}

STATE_COLOURS = {"idle": (52, 101, 164), "listening": (192, 57, 43),
                 "transcribing": (183, 121, 31)}
STATE_TEXT = {"listening": "Listening…  (press the hotkey to stop, Esc to cancel)",
              "transcribing": "Transcribing…"}
REFRESH_SECONDS = 2


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
    def __init__(self, overlay):
        """overlay needs listen(), think() and hide() (see overlay.py)."""
        self.overlay = overlay
        self.hotkey_name = ""
        self.on_quit = None
        self.state = "idle"
        self._images = {s: make_icon(c) for s, c in STATE_COLOURS.items()}
        self._stopped = threading.Event()
        self.icon = None

    def set_state(self, state) -> None:
        self.state = state
        if state == "listening":
            self.overlay.listen()
        elif state == "transcribing":
            self.overlay.think()
        else:
            self.overlay.hide()
        self._refresh()

    def notify(self, message, kind="error") -> None:
        # "info" messages (such as "No speech heard") need nothing extra: the pill
        # simply fades away. Errors pop up from the tray icon.
        if kind == "error":
            log.info("Showing an error notification")
            if self.icon is not None:
                self.icon.notify(message[:250], "Voice Anywhere")

    def status_text(self) -> str:
        if self.state in STATE_TEXT:
            return STATE_TEXT[self.state]
        info = transcriber.status()
        if info["error"]:
            return "Problem: " + info["error"]
        if not info["loaded"]:
            return f"Loading speech model ({info['model']})…"
        return f"Ready: press {self.hotkey_name.title()} to dictate ({self.language_name()})"

    def language_name(self) -> str:
        code = transcriber.language_setting_text()
        return LANGUAGE_SHORT.get(code, code)

    def choose_language(self, code: str) -> None:
        """Called from the Language menu: use this language now and remember it."""
        transcriber.set_language(code)
        settings.save(language=code)
        log.info("Language set to %s", code)
        self._refresh()

    def _title(self) -> str:
        return ("Voice Anywhere: " + self.status_text())[:127]  # Windows tooltip limit

    def _refresh(self) -> None:
        if self.icon is not None:
            self.icon.icon = self._images[self.state]
            self.icon.title = self._title()
            self.icon.update_menu()

    def _keep_status_fresh(self) -> None:
        # Picks up "model loaded" (or a loading problem) once the background preload ends.
        while not self._stopped.wait(REFRESH_SECONDS):
            if self.state == "idle":
                self._refresh()

    def _quit(self, icon=None, item=None) -> None:
        if self.on_quit is not None:
            self.on_quit()
        self._stopped.set()
        if self.icon is not None:
            self.icon.stop()

    def run(self) -> None:
        """Show the tray icon; returns when Quit is chosen."""
        import pystray

        def language_item(label, code):
            return pystray.MenuItem(
                label, lambda icon, item: self.choose_language(code), radio=True,
                checked=lambda item: transcriber.language_setting_text() == code)

        menu = pystray.Menu(
            pystray.MenuItem(lambda item: self.status_text(), None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Language", pystray.Menu(
                *(language_item(label, code) for label, code in LANGUAGES))),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._quit),
        )
        self.icon = pystray.Icon("voice-anywhere", self._images["idle"], self._title(), menu)
        threading.Thread(target=self._keep_status_fresh, name="tray-status", daemon=True).start()
        self.icon.run()
