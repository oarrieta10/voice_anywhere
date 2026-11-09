import pytest


@pytest.fixture(autouse=True)
def private_app_folder(monkeypatch, tmp_path):
    """Every test gets its own empty app folder, so Oscar's real settings and word list are
    never read or changed."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
