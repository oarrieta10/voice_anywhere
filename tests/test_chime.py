import wave

import pytest

from voice_anywhere import chime


@pytest.fixture(autouse=True)
def no_tray_choice(monkeypatch):
    monkeypatch.setattr(chime, "_choice", None)
    monkeypatch.delenv("VOICE_CHIME", raising=False)


def test_sound_file_is_there_and_matches_its_stated_length():
    with wave.open(str(chime.SOUND_FILE)) as sound:
        assert sound.getnframes() / sound.getframerate() == pytest.approx(chime.SECONDS, abs=0.01)


def test_play_hands_the_file_to_the_player():
    played = []
    chime.play(player=played.append)
    assert played == [chime.SOUND_FILE]


def test_a_chime_that_cannot_play_is_not_an_error():
    def broken(path):
        raise OSError("no speakers")

    chime.play(player=broken)


def test_on_off_setting(monkeypatch):
    assert chime.enabled()
    monkeypatch.setenv("VOICE_CHIME", "off")
    assert not chime.enabled()


def test_tray_choice_wins_over_the_variable(monkeypatch):
    monkeypatch.setenv("VOICE_CHIME", "off")
    chime.set_enabled(True)
    assert chime.enabled()


def test_off_means_silent_and_nothing_thrown_away():
    assert chime.skip_seconds() > chime.SECONDS
    chime.set_enabled(False)
    played = []
    chime.play(player=played.append)
    assert played == []
    assert chime.skip_seconds() == 0
