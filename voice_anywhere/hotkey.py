"""Global hotkey through the Win32 RegisterHotKey function (via ctypes, no extra package).

Windows sends a WM_HOTKEY message to the thread that registered the key, so the listener
runs its own thread with a message loop. Esc is registered as a second hotkey only while
recording, so Esc keeps working normally in other programs the rest of the time.
Settings:
  VOICE_HOTKEY  for example "ctrl+alt+space" (default), "ctrl+shift+d", "win+alt+f9"
"""
import ctypes
import os
import threading
from ctypes import wintypes

DEFAULT_HOTKEY = "ctrl+alt+space"

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
WM_HOTKEY, WM_QUIT, WM_APP = 0x0312, 0x0012, 0x8000
WM_ESC_ON, WM_ESC_OFF = WM_APP + 1, WM_APP + 2
VK_ESCAPE = 0x1B
TOGGLE_ID, CANCEL_ID = 1, 2

MODIFIERS = {"ctrl": MOD_CONTROL, "control": MOD_CONTROL, "alt": MOD_ALT,
             "shift": MOD_SHIFT, "win": MOD_WIN, "windows": MOD_WIN}
KEYS = {"space": 0x20, "enter": 0x0D, "return": 0x0D, "tab": 0x09, "esc": VK_ESCAPE,
        "escape": VK_ESCAPE, "backspace": 0x08, "insert": 0x2D, "delete": 0x2E,
        "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22, "pause": 0x13,
        "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27}
KEYS.update({chr(c): c - 32 for c in range(ord("a"), ord("z") + 1)})  # letter keys = upper-case ASCII
KEYS.update({str(d): 0x30 + d for d in range(10)})
KEYS.update({f"f{n}": 0x6F + n for n in range(1, 25)})


class HotkeyError(Exception):
    """Raised for a hotkey that cannot be understood or registered."""


def hotkey_text() -> str:
    return os.environ.get("VOICE_HOTKEY", "").strip() or DEFAULT_HOTKEY


def parse_hotkey(text: str) -> tuple[int, int]:
    """Turn "ctrl+alt+space" into (modifier flags, virtual key code) for RegisterHotKey."""
    parts = [p for p in text.replace(" ", "").lower().split("+") if p]
    if not parts:
        raise HotkeyError("The hotkey is empty")
    *mods, key = parts
    flags = 0
    for mod in mods:
        if mod not in MODIFIERS:
            raise HotkeyError(f"Unknown modifier '{mod}' in hotkey '{text}'")
        flags |= MODIFIERS[mod]
    if key in MODIFIERS:
        raise HotkeyError(f"Hotkey '{text}' needs a key after the modifiers")
    if key not in KEYS:
        raise HotkeyError(f"Unknown key '{key}' in hotkey '{text}'")
    if not flags:
        raise HotkeyError(f"Hotkey '{text}' needs at least one of ctrl, alt, shift or win")
    return flags, KEYS[key]


class HotkeyListener:
    """Calls on_toggle() when the hotkey is pressed and on_cancel() for Esc (when enabled).

    Both callbacks run on the listener thread, so they should return quickly.
    """

    def __init__(self, on_toggle, on_cancel, hotkey=None, user32=None, kernel32=None):
        self.hotkey = hotkey or hotkey_text()
        self.modifiers, self.vk = parse_hotkey(self.hotkey)
        self.on_toggle, self.on_cancel = on_toggle, on_cancel
        self._user32 = user32 or ctypes.WinDLL("user32", use_last_error=True)
        self._kernel32 = kernel32 or ctypes.WinDLL("kernel32", use_last_error=True)
        self._thread = None
        self._thread_id = None
        self._esc_registered = False

    def start(self) -> None:
        """Start listening. Raises HotkeyError if another program already uses the hotkey."""
        ready = threading.Event()
        result = {}

        def run():
            user32 = self._user32
            self._thread_id = self._kernel32.GetCurrentThreadId()
            msg = wintypes.MSG()
            user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)  # creates the message queue
            if not user32.RegisterHotKey(None, TOGGLE_ID, self.modifiers | MOD_NOREPEAT, self.vk):
                result["error"] = HotkeyError(
                    f"Could not register the hotkey {self.hotkey}. "
                    "Another program may already be using it.")
                ready.set()
                return
            ready.set()
            try:
                while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                    self._handle(msg.message, msg.wParam)
            finally:
                self._set_esc(False)
                user32.UnregisterHotKey(None, TOGGLE_ID)

        self._thread = threading.Thread(target=run, name="hotkey", daemon=True)
        self._thread.start()
        ready.wait(5)
        if "error" in result:
            raise result["error"]

    def _handle(self, message, wparam) -> None:
        if message == WM_HOTKEY and wparam == TOGGLE_ID:
            self.on_toggle()
        elif message == WM_HOTKEY and wparam == CANCEL_ID:
            self.on_cancel()
        elif message == WM_ESC_ON:
            self._set_esc(True)
        elif message == WM_ESC_OFF:
            self._set_esc(False)

    def _set_esc(self, on: bool) -> None:
        # Runs on the listener thread: a hotkey belongs to the thread that registered it.
        if on and not self._esc_registered:
            self._esc_registered = bool(
                self._user32.RegisterHotKey(None, CANCEL_ID, MOD_NOREPEAT, VK_ESCAPE))
        elif not on and self._esc_registered:
            self._user32.UnregisterHotKey(None, CANCEL_ID)
            self._esc_registered = False

    def _post(self, message) -> None:
        if self._thread_id is not None:
            self._user32.PostThreadMessageW(self._thread_id, message, 0, 0)

    def enable_cancel(self) -> None:
        """Make Esc cancel (call when recording starts)."""
        self._post(WM_ESC_ON)

    def disable_cancel(self) -> None:
        """Give Esc back to other programs (call when recording ends)."""
        self._post(WM_ESC_OFF)

    def stop(self) -> None:
        self._post(WM_QUIT)
        if self._thread is not None:
            self._thread.join(2)
