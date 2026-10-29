import pytest

from voice_anywhere import hotkey
from voice_anywhere.hotkey import (CANCEL_ID, MOD_ALT, MOD_CONTROL, MOD_NOREPEAT, MOD_SHIFT,
                                   MOD_WIN, TOGGLE_ID, VK_ESCAPE, WM_ESC_OFF, WM_ESC_ON,
                                   WM_HOTKEY, HotkeyError, HotkeyListener, parse_hotkey)


@pytest.mark.parametrize("text, expected", [
    ("ctrl+alt+space", (MOD_CONTROL | MOD_ALT, 0x20)),
    ("Ctrl + Shift + D", (MOD_CONTROL | MOD_SHIFT, ord("D"))),
    ("win+alt+f9", (MOD_WIN | MOD_ALT, 0x78)),
    ("control+7", (MOD_CONTROL, 0x37)),
    ("F9", (0, 0x78)),
    ("pause", (0, 0x13)),
])
def test_parse_hotkey(text, expected):
    assert parse_hotkey(text) == expected


@pytest.mark.parametrize("text", ["", "space", "tab", "a", "ctrl+alt", "ctrl+banana", "hyper+a"])
def test_parse_hotkey_rejects_bad_input(text):
    with pytest.raises(HotkeyError):
        parse_hotkey(text)


def test_hotkey_comes_from_environment(monkeypatch):
    monkeypatch.delenv("VOICE_HOTKEY", raising=False)
    assert hotkey.hotkey_text() == "ctrl+alt+space"
    monkeypatch.setenv("VOICE_HOTKEY", "ctrl+shift+d")
    assert hotkey.hotkey_text() == "ctrl+shift+d"


class FakeUser32:
    """Records hotkey registrations and feeds a scripted list of messages."""

    def __init__(self, messages=(), register_ok=True):
        self.messages = list(messages)
        self.register_ok = register_ok
        self.registered = {}
        self.calls = []
        self.posted = []

    def PeekMessageW(self, *a):
        return 0

    def RegisterHotKey(self, hwnd, ident, mods, vk):
        self.calls.append((ident, mods, vk))
        if self.register_ok:
            self.registered[ident] = (mods, vk)
        return self.register_ok

    def UnregisterHotKey(self, hwnd, ident):
        self.registered.pop(ident, None)
        return 1

    def GetMessageW(self, pmsg, *a):
        if not self.messages:
            return 0  # as if WM_QUIT arrived
        msg = pmsg._obj
        msg.message, msg.wParam = self.messages.pop(0)
        return 1

    def PostThreadMessageW(self, tid, message, w, l):
        self.posted.append((tid, message))
        return 1


class FakeKernel32:
    def GetCurrentThreadId(self):
        return 42


def make_listener(user32, events):
    return HotkeyListener(on_toggle=lambda: events.append("toggle"),
                          on_cancel=lambda: events.append("cancel"),
                          hotkey="ctrl+alt+space", user32=user32, kernel32=FakeKernel32())


def test_message_loop_dispatches_toggle_and_cancel():
    user32 = FakeUser32([(WM_HOTKEY, TOGGLE_ID), (WM_ESC_ON, 0), (WM_HOTKEY, CANCEL_ID),
                         (WM_ESC_OFF, 0), (WM_HOTKEY, TOGGLE_ID)])
    events = []
    listener = make_listener(user32, events)
    listener.start()
    listener._thread.join(2)
    assert events == ["toggle", "cancel", "toggle"]
    assert user32.calls == [
        (TOGGLE_ID, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, 0x20),
        (CANCEL_ID, MOD_NOREPEAT, VK_ESCAPE),
    ]
    assert user32.registered == {}  # everything unregistered when the loop ends


def test_hotkey_in_use_raises():
    listener = make_listener(FakeUser32(register_ok=False), [])
    with pytest.raises(HotkeyError, match="Another program"):
        listener.start()


def test_enable_and_disable_cancel_post_to_listener_thread():
    user32 = FakeUser32()
    listener = make_listener(user32, [])
    listener.start()
    listener.enable_cancel()
    listener.disable_cancel()
    assert user32.posted == [(42, WM_ESC_ON), (42, WM_ESC_OFF)]
