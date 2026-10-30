import numpy as np

from voice_anywhere import chime


def test_chime_is_short_quiet_and_ends_softly():
    samples = chime.make_chime()
    assert samples.dtype == np.float32
    assert len(samples) / chime.PLAY_RATE == chime.SECONDS
    assert np.max(np.abs(samples)) <= chime.VOLUME
    assert abs(samples[0]) < 0.001 and abs(samples[-1]) < 0.001  # no click at either end


def test_skipped_audio_outlasts_the_chime():
    assert chime.SKIP_SECONDS > chime.SECONDS


def test_play_hands_the_samples_to_the_player():
    played = []
    chime.play(player=lambda samples, rate: played.append((len(samples), rate)))
    assert played == [(len(chime.make_chime()), chime.PLAY_RATE)]


def test_a_chime_that_cannot_play_is_not_an_error():
    def broken(samples, rate):
        raise OSError("no speakers")

    chime.play(player=broken)


def test_on_off_setting(monkeypatch):
    monkeypatch.delenv("VOICE_CHIME", raising=False)
    assert chime.enabled()
    monkeypatch.setenv("VOICE_CHIME", "off")
    assert not chime.enabled()
