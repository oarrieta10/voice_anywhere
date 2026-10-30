import queue
import time

import pytest

from voice_anywhere import hotkey
from voice_anywhere.hotkey import (CANCEL_ID, MOD_ALT, MOD_CONTROL, MOD_NOREPEAT, MOD_SHIFT,
                                   MOD_WIN, OUR_KEYPRESS, TAP_SECONDS, TOGGLE_ID, VK_CAPITAL,
                                   VK_ESCAPE, WH_KEYBOARD_LL, WM_ESC_OFF, WM_ESC_ON, WM_HOTKEY,
                                   WM_QUIT, ChordTap, HotkeyError, HotkeyListener,
                                   ShortcutRecorder, check_hotkey, parse_hotkey)


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


class LiveUser32(FakeUser32):
    """A message loop that keeps running, plus a fake keyboard hook."""

    def __init__(self, register_ok=True, caps_on=False):
        super().__init__(register_ok=register_ok)
        self.queue = queue.Queue()
        self.hook = None
        self.caps_on = caps_on
        self.key_presses = []

    def GetMessageW(self, pmsg, *a):
        message = self.queue.get(timeout=5)
        if message == WM_QUIT:
            return 0
        pmsg._obj.message, pmsg._obj.wParam = message, 0
        return 1

    def PostThreadMessageW(self, tid, message, w, l):
        self.queue.put(message)
        return 1

    def SetWindowsHookExW(self, kind, proc, module, thread):
        self.hook = kind
        return 99

    def UnhookWindowsHookEx(self, hook):
        self.hook = None
        return 1

    def GetKeyState(self, vk):
        return 1 if self.caps_on else 0

    def keybd_event(self, vk, scan, flags, extra):
        self.key_presses.append((vk, flags, extra))


def live_listener(user32, events, hotkey="f9"):
    listener = HotkeyListener(on_toggle=lambda: events.append("toggle"), on_cancel=lambda: None,
                              hotkey=hotkey, user32=user32, kernel32=FakeKernel32())
    listener.start()
    return listener


def wait_for(condition):
    for _ in range(200):
        if condition():
            return True
        time.sleep(0.01)
    return False


def test_change_swaps_the_registered_key():
    user32 = LiveUser32()
    listener = live_listener(user32, [])
    listener.change("ctrl+alt+space")
    assert listener.hotkey == "ctrl+alt+space"
    assert user32.registered == {TOGGLE_ID: (MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, 0x20)}
    listener.stop()
    assert user32.registered == {}


def test_change_to_a_hook_hotkey_and_back():
    user32 = LiveUser32()
    listener = live_listener(user32, [])
    listener.change("capslock")
    assert user32.hook == WH_KEYBOARD_LL and user32.registered == {}
    listener.change("f9")
    assert user32.hook is None and user32.registered == {TOGGLE_ID: (MOD_NOREPEAT, 0x78)}
    listener.stop()


def test_change_that_fails_keeps_the_old_hotkey():
    user32 = LiveUser32()
    listener = live_listener(user32, [])
    register = user32.RegisterHotKey
    user32.RegisterHotKey = lambda h, i, mods, vk: 0 if vk == 0x20 else register(h, i, mods, vk)
    with pytest.raises(HotkeyError, match="Another program"):
        listener.change("ctrl+alt+space")
    assert listener.hotkey == "f9"
    assert user32.registered == {TOGGLE_ID: (MOD_NOREPEAT, 0x78)}
    listener.stop()


def test_change_rejects_nonsense_without_touching_anything():
    user32 = LiveUser32()
    listener = live_listener(user32, [])
    with pytest.raises(HotkeyError):
        listener.change("banana")
    assert listener.hotkey == "f9"
    listener.stop()


def test_caps_lock_fires_once_and_is_held_back():
    user32, events = LiveUser32(), []
    listener = live_listener(user32, events, hotkey="capslock")
    assert listener._key_event(VK_CAPITAL, True)
    assert listener._key_event(VK_CAPITAL, True)  # key repeat while held down
    assert listener._key_event(VK_CAPITAL, False)
    assert wait_for(lambda: events == ["toggle"])
    assert not listener._key_event(ord("A"), True)  # other keys pass straight through
    assert events == ["toggle"]
    listener.stop()


def test_capitals_already_on_are_switched_off_when_caps_lock_is_chosen():
    user32 = LiveUser32(caps_on=True)
    listener = live_listener(user32, [], hotkey="capslock")
    assert [(vk, extra) for vk, _, extra in user32.key_presses] == [(VK_CAPITAL, OUR_KEYPRESS)] * 2
    listener.stop()


def test_ctrl_shift_tap_reaches_the_toggle_and_is_never_held_back():
    user32, events = LiveUser32(), []
    listener = live_listener(user32, events, hotkey="ctrl+shift")
    for vk, down in [(VK_LCTRL, True), (VK_LSHIFT, True), (VK_LSHIFT, False), (VK_LCTRL, False)]:
        assert not listener._key_event(vk, down)
    assert wait_for(lambda: events == ["toggle"])
    listener.stop()


VK_LCTRL, VK_LSHIFT, VK_RCTRL, VK_RSHIFT, VK_LALT, VK_WIN = 0xA2, 0xA0, 0xA3, 0xA1, 0xA4, 0x5B


class Clock:
    now = 0.0

    def __call__(self):
        return self.now


def play(tap, *keys):
    """keys are (vk, down) pairs; returns how many of them finished a tap."""
    return sum(tap.key(vk, down) for vk, down in keys)


TAP = ((VK_LCTRL, True), (VK_LSHIFT, True), (VK_LSHIFT, False), (VK_LCTRL, False))


def test_chord_tap_in_either_order_and_with_right_hand_keys():
    tap = ChordTap(clock=Clock())
    assert play(tap, *TAP) == 1
    assert play(tap, (VK_RSHIFT, True), (VK_RCTRL, True), (VK_RSHIFT, False), (VK_RCTRL, False)) == 1


def test_chord_tap_is_not_fooled_by_shortcuts():
    tap = ChordTap(clock=Clock())
    assert play(tap, (VK_LCTRL, True), (VK_LSHIFT, True), (ord("V"), True), (ord("V"), False),
                (VK_LSHIFT, False), (VK_LCTRL, False)) == 0
    assert play(tap, *TAP) == 1  # and the next real tap still works


def test_chord_tap_ignores_a_single_modifier():
    tap = ChordTap(clock=Clock())
    assert play(tap, (VK_LCTRL, True), (ord("C"), True), (ord("C"), False), (VK_LCTRL, False)) == 0
    assert play(tap, (VK_LSHIFT, True), (VK_LSHIFT, False)) == 0


def test_chord_tap_held_too_long_does_not_count():
    clock = Clock()
    tap = ChordTap(clock=clock)
    play(tap, (VK_LCTRL, True), (VK_LSHIFT, True))
    clock.now = TAP_SECONDS + 0.1
    assert play(tap, (VK_LSHIFT, False), (VK_LCTRL, False)) == 0


def test_key_repeat_does_not_restart_the_tap_timer():
    clock = Clock()
    tap = ChordTap(clock=clock)
    play(tap, (VK_LCTRL, True), (VK_LSHIFT, True))
    clock.now = TAP_SECONDS + 0.1
    play(tap, (VK_LSHIFT, True))  # Windows repeats a held key
    assert play(tap, (VK_LSHIFT, False), (VK_LCTRL, False)) == 0


@pytest.mark.parametrize("text", ["capslock", "Caps Lock", "ctrl+shift", "Ctrl + Shift"])
def test_hook_hotkeys_are_accepted(text):
    check_hotkey(text)


def test_tap_works_for_other_modifier_pairs():
    tap = ChordTap(["ctrl", "alt"], clock=Clock())
    assert play(tap, (VK_LCTRL, True), (VK_LALT, True), (VK_LALT, False), (VK_LCTRL, False)) == 1
    assert play(tap, *TAP) == 0  # Shift is not part of this one


def press(recorder, *keys):
    """Hold the keys down in order, then let go in reverse. True if that finished recording."""
    results = [recorder.key(vk, True) for vk in keys]
    results += [recorder.key(vk, False) for vk in reversed(keys)]
    assert not any(results[:-1])  # never finishes while a key is still held
    return results[-1]


@pytest.mark.parametrize("keys, expected", [
    ((VK_LCTRL, VK_LALT, ord("D")), "ctrl+alt+d"),
    ((VK_LALT, VK_LCTRL, ord("D")), "ctrl+alt+d"),  # order of the modifiers does not matter
    ((VK_RCTRL, VK_LSHIFT, 0x77), "ctrl+shift+f8"),
    ((0x77,), "f8"),
    ((0x13,), "pause"),
    ((VK_CAPITAL,), "capslock"),
    ((VK_LSHIFT, 0x78), "shift+f9"),
    ((VK_LCTRL, ord("D")), "ctrl+d"),
    ((VK_LCTRL, VK_LALT), "ctrl+alt"),
    ((VK_LCTRL, VK_WIN), "ctrl+win"),
])
def test_recorder_accepts(keys, expected):
    recorder = ShortcutRecorder()
    assert press(recorder, *keys)
    assert recorder.outcome == (expected, None)
    check_hotkey(expected)


@pytest.mark.parametrize("keys, reason", [
    ((ord("D"),), "needed for typing"),
    ((0x20,), "needed for typing"),
    ((0x09,), "needed for typing"),
    ((VK_LSHIFT, ord("D")), "needed for typing"),
    ((0xBC,), "cannot be used"),  # comma
])
def test_recorder_refuses(keys, reason):
    recorder = ShortcutRecorder()
    assert press(recorder, *keys)
    hotkey, message = recorder.outcome
    assert hotkey is None and reason in message


def test_recorder_esc_cancels_quietly():
    recorder = ShortcutRecorder()
    assert press(recorder, VK_ESCAPE)
    assert recorder.outcome == (None, None)


def test_recorder_keeps_waiting_after_one_modifier():
    recorder = ShortcutRecorder()
    assert not press(recorder, VK_LCTRL)
    assert recorder.outcome is None
    assert press(recorder, VK_LCTRL, ord("D"))
    assert recorder.outcome == ("ctrl+d", None)


def test_recording_holds_keys_back_and_reports_the_result():
    user32, events, results = LiveUser32(), [], []
    listener = live_listener(user32, events)
    listener.record(lambda hotkey, message: results.append((hotkey, message)))
    assert wait_for(lambda: user32.hook == WH_KEYBOARD_LL)
    for vk, down in [(VK_LCTRL, True), (ord("D"), True), (ord("D"), False), (VK_LCTRL, False)]:
        assert listener._key_event(vk, down)
    assert wait_for(lambda: results == [("ctrl+d", None)])
    assert wait_for(lambda: user32.hook is None)  # stops watching straight away
    assert not listener._key_event(ord("D"), True)
    assert listener.hotkey == "f9" and events == []
    listener.stop()


def test_recording_with_a_hook_hotkey_keeps_the_hook_afterwards():
    user32, events, results = LiveUser32(), [], []
    listener = live_listener(user32, events, hotkey="ctrl+shift")
    listener.record(lambda hotkey, message: results.append(hotkey))
    assert listener._key_event(VK_ESCAPE, True) and listener._key_event(VK_ESCAPE, False)
    assert wait_for(lambda: results == [None])
    assert user32.hook == WH_KEYBOARD_LL
    listener.stop()


def test_recording_gives_up_after_the_time_limit(monkeypatch):
    monkeypatch.setattr(hotkey, "RECORD_SECONDS", 0.01)
    user32, results = LiveUser32(), []
    listener = live_listener(user32, [])
    listener.record(lambda hotkey, message: results.append((hotkey, message)))
    assert wait_for(lambda: results == [(None, None)])
    listener.stop()


def test_only_one_recording_at_a_time(monkeypatch):
    user32 = LiveUser32()
    listener = live_listener(user32, [])
    listener.record(lambda hotkey, message: None)
    with pytest.raises(HotkeyError, match="Already"):
        listener.record(lambda hotkey, message: None)
    listener._record_timer.cancel()
    listener.stop()


def test_enable_and_disable_cancel_post_to_listener_thread():
    user32 = FakeUser32()
    listener = make_listener(user32, [])
    listener.start()
    listener.enable_cancel()
    listener.disable_cancel()
    assert user32.posted == [(42, WM_ESC_ON), (42, WM_ESC_OFF)]
