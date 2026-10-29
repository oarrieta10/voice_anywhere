"""Small floating "Listening… / Transcribing…" badge near the bottom of the screen.

It is a borderless tkinter window that is always on top. Windows is told it is a
"no-activate" tool window, and it is shown with ShowWindow(SW_SHOWNOACTIVATE), so it
never takes the keyboard focus from the program Oscar is dictating into and does not
appear in the taskbar or Alt+Tab. All methods must be called on the tkinter thread.
"""
import ctypes
from ctypes import wintypes

GWL_EXSTYLE = -20
WS_EX_TOPMOST, WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE = 0x8, 0x80, 0x08000000
SW_HIDE, SW_SHOWNOACTIVATE = 0, 4
HWND_TOPMOST = -1
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x1, 0x2, 0x10

COLOURS = {"listening": "#c0392b", "transcribing": "#b7791f", "info": "#4a5568"}


class Badge:
    def __init__(self, root):
        import tkinter as tk

        self.root = root
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        self._user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
        self._user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
        self._user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        self._user32.IsWindowVisible.argtypes = [wintypes.HWND]
        self._user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                              ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                              wintypes.UINT]

        self._user32.GetForegroundWindow.restype = wintypes.HWND
        self._user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        previous = self._user32.GetForegroundWindow()

        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.configure(bg=COLOURS["info"])
        self.label = tk.Label(root, text="", fg="white", bg=COLOURS["info"],
                              font=("Segoe UI", 11, "bold"), padx=16, pady=6)
        self.label.pack()
        # Tk creates the real window when it is first drawn; draw it off-screen, then
        # hide it ourselves so Tk keeps painting it while Windows keeps it out of sight.
        root.geometry("+-10000+-10000")
        root.update()
        self.hwnd = int(root.wm_frame(), 16)
        style = self._user32.GetWindowLongPtrW(self.hwnd, GWL_EXSTYLE)
        self._user32.SetWindowLongPtrW(self.hwnd, GWL_EXSTYLE,
                                       style | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TOPMOST)
        self._user32.ShowWindow(self.hwnd, SW_HIDE)
        if previous:  # the first draw may have taken focus; give it back
            self._user32.SetForegroundWindow(previous)

    def show(self, text: str, kind: str = "listening") -> None:
        colour = COLOURS.get(kind, COLOURS["info"])
        self.label.configure(text=text, bg=colour)
        self.root.configure(bg=colour)
        self.root.update_idletasks()
        width, height = self.label.winfo_reqwidth(), self.label.winfo_reqheight()
        screen_w, screen_h = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        x, y = (screen_w - width) // 2, screen_h - height - 90  # just above the taskbar
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self._user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
        self._user32.SetWindowPos(self.hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                                  SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE)

    def hide(self) -> None:
        self._user32.ShowWindow(self.hwnd, SW_HIDE)

    def visible(self) -> bool:
        return bool(self._user32.IsWindowVisible(self.hwnd))
