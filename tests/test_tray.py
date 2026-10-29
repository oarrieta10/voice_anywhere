from voice_anywhere import transcriber, tray
from voice_anywhere.tray import Tray, make_icon


class FakeRoot:
    def __init__(self):
        self.timers = {}
        self.next_id = 0

    def after(self, ms, func, *args):
        self.next_id += 1
        self.timers[self.next_id] = (ms, func)
        return self.next_id

    def after_cancel(self, ident):
        self.timers.pop(ident, None)

    def fire(self, ms):
        for ident, (delay, func) in list(self.timers.items()):
            if delay == ms:
                del self.timers[ident]
                func()


class FakeBadge:
    def __init__(self):
        self.shown = None

    def show(self, text, kind="listening"):
        self.shown = (text, kind)

    def hide(self):
        self.shown = None


def make():
    root, badge = FakeRoot(), FakeBadge()
    return Tray(root, badge), root, badge


def test_badge_follows_state():
    t, root, badge = make()
    t.set_state("listening")
    t._poll()
    assert badge.shown[1] == "listening" and "Listening" in badge.shown[0]
    t.set_state("transcribing")
    t._poll()
    assert badge.shown[1] == "transcribing"
    t.set_state("idle")
    t._poll()
    assert badge.shown is None


def test_info_message_stays_briefly_after_going_idle():
    t, root, badge = make()
    t.set_state("transcribing")
    t.notify("No speech heard", "info")
    t.set_state("idle")
    t._poll()
    assert badge.shown == ("No speech heard", "info")
    root.fire(int(tray.INFO_SECONDS * 1000))
    assert badge.shown is None


def test_quit_runs_on_tk_thread():
    t, root, badge = make()
    calls = []
    t.on_quit = lambda: calls.append("quit")
    t._quit()
    t._poll()
    assert calls == ["quit"]


def test_status_text(monkeypatch):
    t, *_ = make()
    t.hotkey_name = "ctrl+alt+space"
    monkeypatch.setattr(transcriber, "status",
                        lambda: {"available": True, "model": "small", "loaded": False, "error": None})
    assert "Loading" in t.status_text()
    monkeypatch.setattr(transcriber, "status",
                        lambda: {"available": True, "model": "small", "loaded": True, "error": None})
    assert t.status_text() == "Ready: press Ctrl+Alt+Space to dictate"
    t.state = "listening"
    assert "Esc to cancel" in t.status_text()


def test_icons_are_drawn_for_each_state():
    for colour in tray.STATE_COLOURS.values():
        img = make_icon(colour)
        assert img.size == (64, 64)
        assert img.getpixel((5, 32))[:3] == colour
