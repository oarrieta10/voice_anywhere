import ctypes

import pytest

from voice_anywhere import inserter
from voice_anywhere.inserter import Inserter, InserterError


class FakeClipboard:
    def __init__(self, contents, log, fail_on_set=False):
        self.contents = contents
        self.log = log
        self.fail_on_set = fail_on_set

    def save(self):
        self.log.append("save")
        return list(self.contents)

    def set_text(self, text):
        if self.fail_on_set:
            raise InserterError("busy")
        self.log.append(("set", text))
        self.contents = [("text", text)]

    def restore(self, saved):
        self.log.append("restore")
        self.contents = saved


class FakeKeyboard:
    def __init__(self, log):
        self.log = log

    def wait_for_modifiers_released(self):
        self.log.append("wait-keys")

    def send_ctrl_v(self):
        self.log.append("ctrl+v")


class FakeWindows:
    def __init__(self, log, foreground=100, alive=(100, 200)):
        self.log = log
        self.current = foreground
        self.alive = set(alive)

    def foreground(self):
        return self.current

    def exists(self, hwnd):
        return hwnd in self.alive

    def activate(self, hwnd):
        self.log.append(("activate", hwnd))
        self.current = hwnd


def make(log, **kwargs):
    clipboard = FakeClipboard([("old", b"previous")], log, **kwargs)
    windows = FakeWindows(log)
    ins = Inserter(clipboard=clipboard, keyboard=FakeKeyboard(log), windows=windows,
                   sleep=lambda s: log.append(("sleep", s)))
    return ins, clipboard, windows


def test_pastes_into_remembered_window_and_restores_clipboard():
    log = []
    ins, clipboard, windows = make(log)
    ins.remember_target()  # window 100 had focus when recording started
    windows.current = 200  # ...then the user clicked somewhere else
    assert ins.insert("Hello world.") is True
    assert log == [("activate", 100), "wait-keys", "save", ("set", "Hello world."), "ctrl+v",
                   ("sleep", inserter.PASTE_DELAY_SECONDS), "restore"]
    assert clipboard.contents == [("old", b"previous")]


def test_no_activation_when_target_still_has_focus():
    log = []
    ins, _, _ = make(log)
    ins.remember_target()
    ins.insert("hi")
    assert not any(isinstance(e, tuple) and e[0] == "activate" for e in log)


def test_closed_target_window_pastes_into_current_window():
    log = []
    ins, _, windows = make(log)
    ins.remember_target()
    windows.alive.discard(100)
    windows.current = 200
    ins.insert("hi")
    assert "ctrl+v" in log
    assert not any(isinstance(e, tuple) and e[0] == "activate" for e in log)


def test_empty_text_does_nothing():
    log = []
    ins, _, _ = make(log)
    ins.remember_target()
    assert ins.insert("") is False
    assert log == []


def test_clipboard_restored_even_when_paste_fails():
    log = []
    ins, clipboard, _ = make(log, fail_on_set=True)
    ins.remember_target()
    with pytest.raises(InserterError):
        ins.insert("hi")
    assert log[-1] == "restore"
    assert "ctrl+v" not in log


def test_input_structure_has_the_size_windows_expects():
    # SendInput rejects the call if cbSize is wrong: 40 bytes on 64-bit, 28 on 32-bit Windows.
    assert ctypes.sizeof(inserter._INPUT) == (40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)
