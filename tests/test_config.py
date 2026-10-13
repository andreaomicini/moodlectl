import pytest

from moodlectl.config import Settings, normalized_site
from moodlectl.errors import moodlectlError


def test_config_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.delenv("MOODLE_SITE_URL", raising=False)
    settings = Settings.load("unibo")
    settings.course_id = 80509
    settings.save()
    loaded = Settings.load("unibo")
    assert loaded.course_id == 80509
    assert loaded.site == "https://virtuale.unibo.it"
    assert (tmp_path / "config" / "moodlectl" / "unibo.json").exists()


def test_invalid_site_and_profile():
    with pytest.raises(moodlectlError):
        normalized_site("http://insecure.example.com")
    with pytest.raises(moodlectlError):
        Settings.load("../parent")
    assert normalized_site("http://localhost:9090/") == "http://localhost:9090"
