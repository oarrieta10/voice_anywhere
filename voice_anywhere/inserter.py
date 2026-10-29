"""Put text at the cursor in another program: clipboard + Ctrl+V, then put the old clipboard back.

Steps for each dictation:
  1. remember_target() when recording starts notes which window had focus.
  2. insert(text) brings that window back to the front, waits until Ctrl/Alt/Shift/Win
     are released (otherwise our Ctrl+V would become Ctrl+Alt+V), saves the clipboard,
     puts the text on it, sends Ctrl+V with the Win32 SendInput function, waits a moment
     for the program to read it, and restores the saved clipboard.
The dictated text is marked so Windows keeps it out of clipboard history (Win+V) and
cloud clipboard sync.

All Windows calls go through ctypes. Inserter takes the clipboard, keyboard and window
helpers as arguments so tests can pass fakes.
"""
import ctypes
import time
from ctypes import wintypes

PASTE_DELAY_SECONDS = 0.5  # time the target program gets to read the clipboard

CF_UNICODETEXT = 13
# Clipboard formats that hold a GDI (graphics) handle instead of plain memory; they
# cannot be copied byte by byte, so they are skipped when saving.
_HANDLE_FORMATS = {2, 3, 9, 14, 0x80, 0x82, 0x83, 0x8E}
GMEM_MOVEABLE = 0x0002
INPUT_KEYBOARD, KEYEVENTF_KEYUP = 1, 0x0002
VK_CONTROL, VK_V = 0x11, 0x56
_MODIFIER_KEYS = (0x10, 0x11, 0x12, 0x5B, 0x5C)  # Shift, Ctrl, Alt, left Win, right Win


class InserterError(Exception):
    """Raised when the text cannot be pasted."""


class Inserter:
    def __init__(self, clipboard=None, keyboard=None, windows=None,
                 paste_delay=PASTE_DELAY_SECONDS, sleep=time.sleep):
        self.clipboard = clipboard or Win32Clipboard()
        self.keyboard = keyboard or Win32Keyboard()
        self.windows = windows or Win32Windows()
        self.paste_delay = paste_delay
        self.sleep = sleep
        self.target = None

    def remember_target(self) -> None:
        self.target = self.windows.foreground()

    def insert(self, text: str) -> bool:
        """Paste `text` into the remembered window. Returns False if there was nothing to paste."""
        if not text:
            return False
        if self.target and self.windows.exists(self.target) \
                and self.windows.foreground() != self.target:
            self.windows.activate(self.target)
        self.keyboard.wait_for_modifiers_released()
        saved = self.clipboard.save()
        try:
            self.clipboard.set_text(text)
            self.keyboard.send_ctrl_v()
            self.sleep(self.paste_delay)
        finally:
            self.clipboard.restore(saved)
        return True


# --- Real Windows implementations --------------------------------------------------------

def _dlls():
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    # 64-bit handles and pointers need explicit types, or ctypes cuts them to 32 bits.
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.GetClipboardData.restype = wintypes.HANDLE
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.EnumClipboardFormats.argtypes = [wintypes.UINT]
    user32.EnumClipboardFormats.restype = wintypes.UINT
    user32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
    user32.RegisterClipboardFormatW.restype = wintypes.UINT
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.GetAsyncKeyState.restype = ctypes.c_short
    user32.SendInput.argtypes = [wintypes.UINT, ctypes.c_void_p, ctypes.c_int]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalSize.restype = ctypes.c_size_t
    kernel32.GlobalSize.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalFree.restype = wintypes.HGLOBAL
    kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
    return user32, kernel32


class Win32Clipboard:
    def __init__(self):
        self.user32, self.kernel32 = _dlls()
        register = self.user32.RegisterClipboardFormatW
        self._no_history = register("CanIncludeInClipboardHistory")
        self._no_cloud = register("CanUploadToCloudClipboard")

    def _open(self) -> None:
        for _ in range(20):  # another program may have it open for a moment
            if self.user32.OpenClipboard(None):
                return
            time.sleep(0.05)
        raise InserterError("The clipboard is busy (another program is using it)")

    def save(self) -> list[tuple[int, bytes]]:
        """Copy every plain-memory format currently on the clipboard."""
        self._open()
        saved = []
        try:
            fmt = self.user32.EnumClipboardFormats(0)
            while fmt:
                if fmt not in _HANDLE_FORMATS:
                    data = self._read(fmt)
                    if data is not None:
                        saved.append((fmt, data))
                fmt = self.user32.EnumClipboardFormats(fmt)
        finally:
            self.user32.CloseClipboard()
        return saved

    def _read(self, fmt):
        handle = self.user32.GetClipboardData(fmt)
        if not handle:
            return None
        size = self.kernel32.GlobalSize(handle)
        ptr = self.kernel32.GlobalLock(handle)
        if not ptr:
            return None
        try:
            return ctypes.string_at(ptr, size)
        finally:
            self.kernel32.GlobalUnlock(handle)

    def _put(self, fmt: int, data: bytes) -> None:
        handle = self.kernel32.GlobalAlloc(GMEM_MOVEABLE, max(len(data), 1))
        if not handle:
            return
        ptr = self.kernel32.GlobalLock(handle)
        ctypes.memmove(ptr, data, len(data))
        self.kernel32.GlobalUnlock(handle)
        if not self.user32.SetClipboardData(fmt, handle):
            self.kernel32.GlobalFree(handle)  # Windows only takes ownership on success

    def _replace(self, items) -> None:
        self._open()
        try:
            self.user32.EmptyClipboard()
            for fmt, data in items:
                self._put(fmt, data)
        finally:
            self.user32.CloseClipboard()

    def set_text(self, text: str) -> None:
        zero = (0).to_bytes(4, "little")  # DWORD 0 = "no"
        self._replace([(CF_UNICODETEXT, (text + "\0").encode("utf-16-le")),
                       (self._no_history, zero), (self._no_cloud, zero)])

    def restore(self, saved) -> None:
        self._replace(saved)


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


class _INPUTUNION(ctypes.Union):
    # The mouse member is the largest; it is here so the structure has the size Windows expects.
    _fields_ = [("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


class Win32Keyboard:
    def __init__(self):
        self.user32, _ = _dlls()

    def wait_for_modifiers_released(self, timeout=3.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not any(self.user32.GetAsyncKeyState(vk) & 0x8000 for vk in _MODIFIER_KEYS):
                return
            time.sleep(0.02)

    def send_ctrl_v(self) -> None:
        keys = [(VK_CONTROL, 0), (VK_V, 0), (VK_V, KEYEVENTF_KEYUP), (VK_CONTROL, KEYEVENTF_KEYUP)]
        inputs = (_INPUT * len(keys))()
        for item, (vk, flags) in zip(inputs, keys):
            item.type = INPUT_KEYBOARD
            item.u.ki = _KEYBDINPUT(wVk=vk, dwFlags=flags)
        sent = self.user32.SendInput(len(keys), inputs, ctypes.sizeof(_INPUT))
        if sent != len(keys):
            raise InserterError("Windows blocked the Ctrl+V keystroke")


class Win32Windows:
    def __init__(self):
        self.user32, _ = _dlls()

    def foreground(self):
        return self.user32.GetForegroundWindow()

    def exists(self, hwnd) -> bool:
        return bool(self.user32.IsWindow(hwnd))

    def activate(self, hwnd) -> None:
        self.user32.SetForegroundWindow(hwnd)
