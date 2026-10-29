import pytest

from voice_anywhere import settings


@pytest.fixture(autouse=True)
def own_folder(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    return tmp_path


def test_nothing_saved_yet():
    assert settings.load() == {}


def test_save_and_load_keeps_other_settings():
    settings.save(language="es")
    settings.save(other="x")
    assert settings.load() == {"language": "es", "other": "x"}
    settings.save(language="en")
    assert settings.load()["language"] == "en"


def test_damaged_file_is_ignored(own_folder):
    (own_folder / "voice-anywhere").mkdir(exist_ok=True)
    (own_folder / "voice-anywhere" / "settings.json").write_text("{not json", encoding="utf-8")
    assert settings.load() == {}
    settings.save(language="es")  # and it can be written again
    assert settings.load() == {"language": "es"}
