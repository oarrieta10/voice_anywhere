from voice_anywhere import transcriber, tray
from voice_anywhere.tray import Tray, make_icon


class FakeOverlay:
    def __init__(self):
        self.log = []

    def listen(self):
        self.log.append("listen")

    def think(self):
        self.log.append("think")

    def hide(self):
        self.log.append("hide")


def test_pill_follows_state():
    overlay = FakeOverlay()
    t = Tray(overlay)
    for state in ("listening", "transcribing", "idle"):
        t.set_state(state)
    assert overlay.log == ["listen", "think", "hide"]


def test_info_message_needs_no_popup():
    t = Tray(FakeOverlay())

    class FakeIcon:
        notes = []

        def notify(self, message, title):
            self.notes.append(message)

    t.icon = FakeIcon()
    t.notify("No speech heard", "info")
    assert FakeIcon.notes == []
    t.notify("Could not open the microphone", "error")
    assert FakeIcon.notes == ["Could not open the microphone"]


def test_quit_calls_on_quit_and_stops_icon():
    t = Tray(FakeOverlay())
    calls = []

    class FakeIcon:
        def stop(self):
            calls.append("icon stopped")

    t.icon = FakeIcon()
    t.on_quit = lambda: calls.append("quit")
    t._quit()
    assert calls == ["quit", "icon stopped"]


def test_status_text(monkeypatch):
    t = Tray(FakeOverlay())
    t.hotkey_name = "f9"
    monkeypatch.setattr(transcriber, "status",
                        lambda: {"available": True, "model": "small", "loaded": False, "error": None})
    assert "Loading" in t.status_text()
    monkeypatch.setattr(transcriber, "status",
                        lambda: {"available": True, "model": "small", "loaded": True, "error": None})
    assert t.status_text().startswith("Ready: press F9 to dictate (")
    t.state = "listening"
    assert "Esc to cancel" in t.status_text()


def test_choosing_a_language_applies_and_remembers_it(monkeypatch, tmp_path):
    from voice_anywhere import settings

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("VOICE_WHISPER_LANG", "en,es")
    monkeypatch.setattr(transcriber, "_language_choice", None)
    monkeypatch.setattr(transcriber, "status",
                        lambda: {"available": True, "model": "small", "loaded": True, "error": None})
    t = Tray(FakeOverlay())
    t.hotkey_name = "f9"
    assert t.status_text().endswith("(English or Spanish)")
    t.choose_language("es")
    assert transcriber.language() == "es"
    assert settings.load() == {"language": "es"}
    assert t.status_text() == "Ready: press F9 to dictate (Spanish)"


def test_every_menu_language_has_a_short_name():
    for _, code in tray.LANGUAGES:
        assert code in tray.LANGUAGE_SHORT


def test_icons_are_drawn_for_each_state():
    for colour in tray.STATE_COLOURS.values():
        img = make_icon(colour)
        assert img.size == (64, 64)
        assert img.getpixel((0, 0))[3] == 0  # transparent background
        assert img.getpixel((32, 56)) == (*colour, 255)  # the stand


def test_icon_is_red_only_while_listening():
    assert tray.STATE_COLOURS["idle"] == (0, 0, 0)
    assert tray.STATE_COLOURS["transcribing"] == (0, 0, 0)
    red, green, blue = tray.STATE_COLOURS["listening"]
    assert red > 200 and green < 60 and blue < 60
