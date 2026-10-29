"""Shows the pill (pill.py) in the bottom-right corner of the screen, above the taskbar.

The pill lives in a Windows "layered" window: each frame is handed to Windows as a picture
with its own transparency (UpdateLayeredWindow), which gives smooth rounded edges and
fades. The window is also:
  - no-activate: it never takes the keyboard focus from the program being dictated into,
  - click-through: mouse clicks go to whatever is underneath,
  - a tool window: it is not shown in the taskbar or Alt+Tab,
  - topmost: it stays above other windows.
It runs on its own thread, drawing about 30 frames a second while visible and sleeping
while hidden. listen(), think(), hide() and set_level() may be called from any thread.
All Windows calls go through ctypes.
"""
import ctypes
import logging
import threading
import time
from ctypes import wintypes

import numpy as np

from .pill import PillAnimator, canvas_size

log = logging.getLogger("voice_anywhere")

FPS = 30
CORNER_GAP = 16  # space between the pill and the screen edge / taskbar, at 100% scaling

WS_POPUP = 0x80000000
WS_EX_TOPMOST, WS_EX_TRANSPARENT, WS_EX_TOOLWINDOW = 0x8, 0x20, 0x80
WS_EX_LAYERED, WS_EX_NOACTIVATE = 0x80000, 0x08000000
SW_HIDE, SW_SHOWNOACTIVATE = 0, 4
HWND_TOPMOST = -1
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x1, 0x2, 0x10
ULW_ALPHA, AC_SRC_OVER, AC_SRC_ALPHA = 0x2, 0x0, 0x1
SPI_GETWORKAREA = 0x30
PM_REMOVE = 0x1
DIB_RGB_COLORS, BI_RGB = 0, 0


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


def to_windows_pixels(img) -> bytes:
    """Pillow RGBA picture -> the byte layout UpdateLayeredWindow wants.

    Windows wants blue-green-red-alpha order, with each colour already multiplied by
    its transparency ("premultiplied alpha").
    """
    arr = np.asarray(img.convert("RGBA"), dtype=np.uint16)
    alpha = arr[..., 3:4]
    rgb = (arr[..., :3] * alpha + 127) // 255
    out = np.empty(arr.shape, dtype=np.uint8)
    out[..., 0], out[..., 1], out[..., 2] = rgb[..., 2], rgb[..., 1], rgb[..., 0]
    out[..., 3] = alpha[..., 0]
    return out.tobytes()


def _dlls():
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    # 64-bit handles and pointers need explicit types, or ctypes cuts them to 32 bits.
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                       wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                       ctypes.c_int, wintypes.HWND, wintypes.HMENU,
                                       wintypes.HINSTANCE, wintypes.LPVOID]
    user32.UpdateLayeredWindow.argtypes = [wintypes.HWND, wintypes.HDC,
                                           ctypes.POINTER(wintypes.POINT),
                                           ctypes.POINTER(wintypes.SIZE), wintypes.HDC,
                                           ctypes.POINTER(wintypes.POINT), wintypes.COLORREF,
                                           ctypes.POINTER(BLENDFUNCTION), wintypes.DWORD]
    user32.GetDC.restype = wintypes.HDC
    user32.GetDC.argtypes = [wintypes.HWND]
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, wintypes.UINT]
    user32.DestroyWindow.argtypes = [wintypes.HWND]
    user32.SystemParametersInfoW.argtypes = [wintypes.UINT, wintypes.UINT, wintypes.LPVOID,
                                             wintypes.UINT]
    user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT,
                                    wintypes.UINT, wintypes.UINT]
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.CreateDIBSection.restype = wintypes.HBITMAP
    gdi32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.POINTER(BITMAPINFO), wintypes.UINT,
                                       ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE,
                                       wintypes.DWORD]
    gdi32.SelectObject.restype = wintypes.HGDIOBJ
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi32.DeleteDC.argtypes = [wintypes.HDC]
    return user32, gdi32


def display_scale(user32) -> float:
    """Windows display scaling: 1.0 at 100%, 1.5 at 150%, ..."""
    try:
        return user32.GetDpiForSystem() / 96
    except (AttributeError, OSError):
        return 1.0


class Overlay:
    def __init__(self):
        self.user32, self.gdi32 = _dlls()
        self.scale = display_scale(self.user32)
        self.animator = PillAnimator(self.scale)
        self.width, self.height = canvas_size(self.scale)
        self._wake = threading.Event()
        self._running = False
        self._thread = None

    # --- called from any thread ---

    def listen(self) -> None:
        self.animator.listen()
        self._wake.set()

    def think(self) -> None:
        self.animator.think()
        self._wake.set()

    def hide(self) -> None:
        self.animator.hide()
        self._wake.set()

    def set_level(self, level: float) -> None:
        self.animator.set_level(level)

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._run, name="overlay", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        self._wake.set()
        if self._thread is not None:
            self._thread.join(2)

    # --- overlay thread ---

    def _corner(self) -> tuple[int, int]:
        """Top-left position that puts the pill in the bottom-right corner, above the taskbar."""
        work = wintypes.RECT()
        self.user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(work), 0)
        gap = round(CORNER_GAP * self.scale)
        return work.right - self.width - gap, work.bottom - self.height - gap

    def _run(self) -> None:
        u, g = self.user32, self.gdi32
        x, y = self._corner()
        hwnd = u.CreateWindowExW(
            WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_TOPMOST | WS_EX_NOACTIVATE,
            "Static", None, WS_POPUP, x, y, self.width, self.height, None, None, None, None)
        if not hwnd:
            log.warning("Could not create the overlay window (error %d)", ctypes.get_last_error())
            return
        screen_dc = u.GetDC(None)
        mem_dc = g.CreateCompatibleDC(screen_dc)
        info = BITMAPINFO()
        h = info.bmiHeader
        h.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        h.biWidth, h.biHeight = self.width, -self.height  # negative: rows run top to bottom
        h.biPlanes, h.biBitCount, h.biCompression = 1, 32, BI_RGB
        bits = ctypes.c_void_p()
        bitmap = g.CreateDIBSection(screen_dc, ctypes.byref(info), DIB_RGB_COLORS,
                                    ctypes.byref(bits), None, 0)
        old = g.SelectObject(mem_dc, bitmap)
        size = wintypes.SIZE(self.width, self.height)
        src = wintypes.POINT(0, 0)
        blend = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
        msg = wintypes.MSG()
        visible = False
        try:
            while self._running:
                while u.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                    u.TranslateMessage(ctypes.byref(msg))
                    u.DispatchMessageW(ctypes.byref(msg))
                started = time.perf_counter()
                frame = self.animator.frame(started)
                if frame is None:
                    if visible:
                        u.ShowWindow(hwnd, SW_HIDE)
                        visible = False
                    self._wake.wait(0.5)
                    self._wake.clear()
                    continue
                if not visible:
                    x, y = self._corner()  # the taskbar or screen may have changed
                ctypes.memmove(bits, to_windows_pixels(frame), self.width * self.height * 4)
                pos = wintypes.POINT(x, y)
                u.UpdateLayeredWindow(hwnd, screen_dc, ctypes.byref(pos), ctypes.byref(size),
                                      mem_dc, ctypes.byref(src), 0, ctypes.byref(blend),
                                      ULW_ALPHA)
                if not visible:
                    u.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
                    u.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                                   SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE)
                    visible = True
                pause = 1 / FPS - (time.perf_counter() - started)
                if pause > 0:
                    self._wake.wait(pause)
                    self._wake.clear()
        finally:
            g.SelectObject(mem_dc, old)
            g.DeleteObject(bitmap)
            g.DeleteDC(mem_dc)
            u.ReleaseDC(None, screen_dc)
            u.DestroyWindow(hwnd)
