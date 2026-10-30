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

    def prompt(self, text):
        self.log.append("prompt")


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


def test_chime_item_flips_and_remembers(monkeypatch, tmp_path):
    from voice_anywhere import chime, settings

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("VOICE_CHIME", raising=False)
    monkeypatch.setattr(chime, "_choice", None)
    t = Tray(FakeOverlay())
    t.toggle_chime()
    assert not chime.enabled()
    assert settings.load() == {"chime": False}
    t.toggle_chime()
    assert chime.enabled()
    assert settings.load() == {"chime": True}


def test_choosing_a_shortcut_applies_and_remembers_it(monkeypatch, tmp_path):
    from voice_anywhere import settings

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(transcriber, "status",
                        lambda: {"available": True, "model": "small", "loaded": True, "error": None})
    t = Tray(FakeOverlay())
    t.hotkey_name = "f9"
    changes = []
    t.on_hotkey_change = changes.append
    t.choose_shortcut("capslock")
    assert changes == ["capslock"]
    assert t.hotkey_name == "capslock"
    assert settings.load() == {"hotkey": "capslock"}
    assert t.status_text().startswith("Ready: press Caps Lock to dictate")


def test_shortcut_that_fails_changes_nothing_and_says_why(monkeypatch, tmp_path):
    from voice_anywhere import settings
    from voice_anywhere.hotkey import HotkeyError

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    t = Tray(FakeOverlay())
    t.hotkey_name = "f9"

    class FakeIcon:
        notes = []

        def notify(self, message, title):
            self.notes.append(message)

        def update_menu(self):
            pass

    def taken(code):
        raise HotkeyError("Another program may already be using it.")

    t.icon = FakeIcon()
    t.on_hotkey_change = taken
    t.choose_shortcut("ctrl+shift")
    assert t.hotkey_name == "f9"
    assert settings.load() == {}
    assert FakeIcon.notes == ["Another program may already be using it."]


def test_recorded_shortcut_is_applied_and_remembered(monkeypatch, tmp_path):
    from voice_anywhere import settings

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    overlay = FakeOverlay()
    t = Tray(overlay)
    t.hotkey_name = "f9"
    t.on_record_shortcut = lambda done: done("ctrl+alt+d", None)
    t.on_hotkey_change = lambda code: None
    t.record_shortcut()
    assert overlay.log == ["prompt", "hide"]
    assert t.hotkey_name == "ctrl+alt+d"
    assert t.hotkey_label() == "Ctrl+Alt+D"
    assert settings.load() == {"hotkey": "ctrl+alt+d"}


def test_refused_shortcut_changes_nothing_and_says_why(monkeypatch, tmp_path):
    from voice_anywhere import settings

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    t = Tray(FakeOverlay())
    t.hotkey_name = "f9"
    notes = []
    t.notify = lambda message, kind="error": notes.append(message)
    t.on_record_shortcut = lambda done: done(None, "D on its own is needed for typing.")
    t.record_shortcut()
    assert t.hotkey_name == "f9"
    assert settings.load() == {}
    assert notes == ["D on its own is needed for typing."]


def test_recording_refused_during_dictation_hides_the_prompt():
    from voice_anywhere.hotkey import HotkeyError

    overlay = FakeOverlay()
    t = Tray(overlay)
    notes = []
    t.notify = lambda message, kind="error": notes.append(message)

    def busy(done):
        raise HotkeyError("Finish the dictation first")

    t.on_record_shortcut = busy
    t.record_shortcut()
    assert overlay.log == ["prompt", "hide"] and notes == ["Finish the dictation first"]


def test_shortcut_names_read_well():
    t = Tray(FakeOverlay())
    for code, label in [("f9", "F9"), ("capslock", "Caps Lock"), ("ctrl+shift", "Ctrl+Shift")]:
        t.hotkey_name = code
        assert t.hotkey_label() == label


def test_every_menu_language_has_a_short_name():
    for _, code in tray.LANGUAGES:
        assert code in tray.LANGUAGE_SHORT


def test_icons_are_drawn_for_each_state():
    for colour in tray.STATE_COLOURS.values():
        img = make_icon(colour)
        assert img.size == (64, 64)
        assert img.getpixel((0, 0))[3] == 0  # transparent background
        *rgb, alpha = img.getpixel((32, 56))  # the stand
        # Smoothing can shift a value by a point or two.
        assert all(abs(got - want) <= 2 for got, want in zip(rgb, colour)) and alpha > 240


def test_icon_is_red_only_while_listening():
    assert tray.STATE_COLOURS["idle"] == (0, 0, 0)
    assert tray.STATE_COLOURS["transcribing"] == (0, 0, 0)
    red, green, blue = tray.STATE_COLOURS["listening"]
    assert red > 200 and green < 60 and blue < 60
