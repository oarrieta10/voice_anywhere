"""Global hotkey through the Win32 RegisterHotKey function (via ctypes, no extra package).

Windows sends a WM_HOTKEY message to the thread that registered the key, so the listener
runs its own thread with a message loop. Esc is registered as a second hotkey only while
recording, so Esc keeps working normally in other programs the rest of the time.

Two hotkeys cannot work through RegisterHotKey, so they use a Windows keyboard hook
(SetWindowsHookEx) that runs only while one of them is chosen:
  - capslock: the key must be stopped before it reaches Windows, or capitals switch on too.
  - ctrl+shift: it only counts as a quick tap of those two keys with nothing else pressed,
    so that shortcuts such as Ctrl+Shift+V keep working.
The hook sees every key press, but only compares it with these keys. Nothing is stored or
logged, and no key other than Caps Lock is ever held back.
Settings:
  VOICE_HOTKEY  for example "ctrl+alt+space" (default), "ctrl+shift+d", "f9", "capslock"
"""
import ctypes
import os
import threading
import time
from ctypes import wintypes

DEFAULT_HOTKEY = "ctrl+alt+space"

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
WM_HOTKEY, WM_QUIT, WM_APP = 0x0312, 0x0012, 0x8000
WM_ESC_ON, WM_ESC_OFF, WM_RUN_TOGGLE, WM_CHANGE = WM_APP + 1, WM_APP + 2, WM_APP + 3, WM_APP + 4
WM_KEYDOWN, WM_SYSKEYDOWN = 0x100, 0x104
WH_KEYBOARD_LL = 13
KEYEVENTF_KEYUP = 0x2
VK_ESCAPE, VK_CAPITAL = 0x1B, 0x14
CTRL_KEYS, SHIFT_KEYS = {0x11, 0xA2, 0xA3}, {0x10, 0xA0, 0xA1}
TOGGLE_ID, CANCEL_ID = 1, 2
TAP_SECONDS = 0.5  # holding Ctrl+Shift longer than this is not a tap
OUR_KEYPRESS = 0x564F4943  # marks the Caps Lock press the app sends itself

MODIFIERS = {"ctrl": MOD_CONTROL, "control": MOD_CONTROL, "alt": MOD_ALT,
             "shift": MOD_SHIFT, "win": MOD_WIN, "windows": MOD_WIN}
KEYS = {"space": 0x20, "enter": 0x0D, "return": 0x0D, "tab": 0x09, "esc": VK_ESCAPE,
        "escape": VK_ESCAPE, "backspace": 0x08, "insert": 0x2D, "delete": 0x2E,
        "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22, "pause": 0x13,
        "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27}
KEYS.update({chr(c): c - 32 for c in range(ord("a"), ord("z") + 1)})  # letter keys = upper-case ASCII
KEYS.update({str(d): 0x30 + d for d in range(10)})
KEYS.update({f"f{n}": 0x6F + n for n in range(1, 25)})
# Keys that may be used on their own: rarely needed for typing, so taking one over for
# dictation costs little. Every other key needs a modifier.
SOLO_KEYS = {f"f{n}" for n in range(1, 25)} | {"pause", "insert"}
HOOK_HOTKEYS = {"capslock", "ctrl+shift"}  # these need the keyboard hook


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
                ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)


class HotkeyError(Exception):
    """Raised for a hotkey that cannot be understood or registered."""


def hotkey_text() -> str:
    return os.environ.get("VOICE_HOTKEY", "").strip() or DEFAULT_HOTKEY


def _name(text: str) -> str:
    return text.replace(" ", "").lower()


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
    if not flags and key not in SOLO_KEYS:
        raise HotkeyError(f"Hotkey '{text}' needs at least one of ctrl, alt, shift or win "
                          "(only f1-f24, pause and insert can be used on their own)")
    return flags, KEYS[key]


def check_hotkey(text: str) -> None:
    """Raises HotkeyError if this is not a hotkey the listener can use."""
    if _name(text) not in HOOK_HOTKEYS:
        parse_hotkey(text)


class ChordTap:
    """Recognises a quick tap of Ctrl+Shift with nothing else pressed.

    It fires when the last of the two keys is let go. Any other key pressed meanwhile
    (Ctrl+Shift+V) or holding them too long (Ctrl+Shift+click) cancels it.
    """

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self._held = set()
        self._both_since = None
        self._spoiled = False

    def key(self, vk, down) -> bool:
        """Report a key going down or up. True means the tap just finished."""
        kind = "ctrl" if vk in CTRL_KEYS else "shift" if vk in SHIFT_KEYS else None
        if kind is None:
            if down and self._held:
                self._spoiled = True
            return False
        if down:
            self._held.add(kind)
            if len(self._held) == 2 and self._both_since is None:
                self._both_since = self.clock()
            return False
        self._held.discard(kind)
        if self._held:
            return False
        tapped = (self._both_since is not None and not self._spoiled
                  and self.clock() - self._both_since <= TAP_SECONDS)
        self._both_since, self._spoiled = None, False
        return tapped


def _real_user32():
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    # 64-bit handles and pointers need explicit types, or ctypes cuts them to 32 bits.
    user32.SetWindowsHookExW.restype = wintypes.HHOOK
    user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
    user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
    user32.CallNextHookEx.restype = LRESULT
    user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
    user32.keybd_event.argtypes = [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ctypes.c_size_t]
    return user32


class HotkeyListener:
    """Calls on_toggle() when the hotkey is pressed and on_cancel() for Esc (when enabled).

    Both callbacks run on the listener thread, so they should return quickly.
    """

    def __init__(self, on_toggle, on_cancel, hotkey=None, user32=None, kernel32=None):
        self.hotkey = hotkey or hotkey_text()
        check_hotkey(self.hotkey)
        self.on_toggle, self.on_cancel = on_toggle, on_cancel
        self._user32 = user32 or _real_user32()
        self._kernel32 = kernel32 or ctypes.WinDLL("kernel32", use_last_error=True)
        self._thread = None
        self._thread_id = None
        self._esc_registered = False
        self._hook = None
        self._hook_proc = None  # must stay alive as long as the hook does
        self._watching = None
        self._tap = ChordTap()
        self._caps_down = False
        self._change = None

    def start(self) -> None:
        """Start listening. Raises HotkeyError if another program already uses the hotkey."""
        ready = threading.Event()
        result = {}

        def run():
            user32 = self._user32
            self._thread_id = self._kernel32.GetCurrentThreadId()
            msg = wintypes.MSG()
            user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)  # creates the message queue
            try:
                self._bind(self.hotkey)
            except HotkeyError as exc:
                result["error"] = exc
                ready.set()
                return
            ready.set()
            try:
                while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                    self._handle(msg.message, msg.wParam)
            finally:
                self._set_esc(False)
                self._unbind()

        self._thread = threading.Thread(target=run, name="hotkey", daemon=True)
        self._thread.start()
        ready.wait(5)
        if "error" in result:
            raise result["error"]

    def change(self, text: str) -> None:
        """Switch to another hotkey. If it cannot be used, raises HotkeyError and keeps the old one."""
        check_hotkey(text)
        self._change = {"text": text, "done": threading.Event(), "error": None}
        self._post(WM_CHANGE)
        if not self._change["done"].wait(5):
            raise HotkeyError("Could not change the hotkey: no response")
        if self._change["error"]:
            raise self._change["error"]

    # --- listener thread ---

    def _bind(self, text: str) -> None:
        if _name(text) in HOOK_HOTKEYS:
            self._start_hook(_name(text))
            return
        modifiers, vk = parse_hotkey(text)
        if not self._user32.RegisterHotKey(None, TOGGLE_ID, modifiers | MOD_NOREPEAT, vk):
            raise HotkeyError(f"Could not register the hotkey {text}. "
                              "Another program may already be using it.")

    def _unbind(self) -> None:
        self._user32.UnregisterHotKey(None, TOGGLE_ID)
        if self._hook is not None:
            self._user32.UnhookWindowsHookEx(self._hook)
            self._hook = self._hook_proc = self._watching = None

    def _start_hook(self, name: str) -> None:
        user32 = self._user32
        self._watching = name
        self._tap, self._caps_down = ChordTap(), False
        self._hook_proc = HOOKPROC(self._on_hook)
        self._hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._hook_proc, None, 0)
        if not self._hook:
            self._hook_proc = self._watching = None
            raise HotkeyError(f"Could not set up the hotkey {name}.")
        if name == "capslock" and user32.GetKeyState(VK_CAPITAL) & 1:
            # Capitals were on: switch them off now, as this key can no longer do it.
            user32.keybd_event(VK_CAPITAL, 0x3A, 0, OUR_KEYPRESS)
            user32.keybd_event(VK_CAPITAL, 0x3A, KEYEVENTF_KEYUP, OUR_KEYPRESS)

    def _on_hook(self, code, wparam, lparam):
        # Windows calls this for every key, so it only decides and returns: the actual
        # work happens in the message loop. Returning 1 stops the key going any further.
        if code >= 0:
            info = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            down = wparam in (WM_KEYDOWN, WM_SYSKEYDOWN)
            if info.dwExtraInfo != OUR_KEYPRESS and self._key_event(info.vkCode, down):
                return 1
        return self._user32.CallNextHookEx(None, code, wparam, lparam)

    def _key_event(self, vk, down) -> bool:
        """Act on one key. True means hold this key back from Windows."""
        if self._watching == "capslock":
            if vk != VK_CAPITAL:
                return False
            if down and not self._caps_down:
                self._post(WM_RUN_TOGGLE)
            self._caps_down = down
            return True
        if self._tap.key(vk, down):
            self._post(WM_RUN_TOGGLE)
        return False

    def _switch(self) -> None:
        change, old = self._change, self.hotkey
        self._unbind()
        try:
            self._bind(change["text"])
            self.hotkey = change["text"]
        except HotkeyError as exc:
            change["error"] = exc
            self._bind(old)
        change["done"].set()

    def _handle(self, message, wparam) -> None:
        if message == WM_RUN_TOGGLE or (message == WM_HOTKEY and wparam == TOGGLE_ID):
            self.on_toggle()
        elif message == WM_CHANGE:
            self._switch()
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
