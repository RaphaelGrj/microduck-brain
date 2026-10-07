"""Les tests n'ecrivent jamais dans ~/.local/share/microduck (messages, photos) : un dossier temporaire par test."""
import pytest


@pytest.fixture(autouse=True)
def _dossiers_temporaires(tmp_path, monkeypatch):
    monkeypatch.setenv("MICRODUCK_MESSAGES", str(tmp_path / "messages.json"))
    monkeypatch.setenv("MICRODUCK_PHOTOS", str(tmp_path / "photos"))
    monkeypatch.setenv("MICRODUCK_JEUX", str(tmp_path / "jeux.json"))
    monkeypatch.setenv("MICRODUCK_CARNET", str(tmp_path / "carnet.json"))
    monkeypatch.setenv("MICRODUCK_INVITES", str(tmp_path / "invites.json"))
    monkeypatch.setenv("MICRODUCK_PLANNING", str(tmp_path / "planning.json"))
