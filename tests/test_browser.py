from types import SimpleNamespace

import pytest
from playwright.sync_api import Error as PWError

from moodlectl import browser as browser_mod
from moodlectl.browser import BrowserMoodle
from moodlectl.config import Settings
from moodlectl.errors import moodlectlError


class FakePlaywright:
    def __init__(self, installed):
        self.installed = installed
        self.tried = []
        self.jar = []
        for engine in ("chromium", "firefox", "webkit"):
            setattr(self, engine, SimpleNamespace(launch_persistent_context=self._launcher(engine)))

    def _launcher(self, engine):
        return lambda _dir, *, channel=None, **_: self.launch(channel or engine)

    def start(self):
        return self

    def stop(self):
        pass

    def launch(self, channel):
        self.tried.append(channel)
        if channel not in self.installed:
            raise PWError(f"Chromium distribution '{channel}' is not found")
        page = SimpleNamespace(set_default_timeout=lambda _ms: None)
        return SimpleNamespace(
            pages=[page], close=lambda: None, cookies=lambda: self.jar, add_cookies=self.jar.extend
        )


def _settings(tmp_path, monkeypatch, browser):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    settings = Settings(profile="test")
    settings.browser = browser
    return settings


@pytest.mark.parametrize(
    "platform, first", [("darwin", "webkit"), ("win32", "msedge"), ("linux", "firefox")]
)
def test_auto_prefers_os_browser_then_falls_back(tmp_path, monkeypatch, platform, first):
    monkeypatch.setattr(browser_mod.sys, "platform", platform)
    fake = FakePlaywright(installed={"chrome"})
    monkeypatch.setattr(browser_mod, "sync_playwright", lambda: fake)
    with BrowserMoodle(_settings(tmp_path, monkeypatch, "auto")):
        assert fake.tried == [first, "chromium", "chrome"]


def test_explicit_browser_missing_reports_error(tmp_path, monkeypatch):
    fake = FakePlaywright(installed={"chromium"})
    monkeypatch.setattr(browser_mod, "sync_playwright", lambda: fake)
    with pytest.raises(moodlectlError, match="chrome"):
        with BrowserMoodle(_settings(tmp_path, monkeypatch, "chrome")):
            pass
    assert fake.tried == ["chrome"]


def test_session_cookies_survive_restart(tmp_path, monkeypatch):
    settings = _settings(tmp_path, monkeypatch, "auto")
    first = FakePlaywright(installed={"chromium"})
    first.jar += [{"name": "MoodleSession", "expires": -1}, {"name": "kept", "expires": 2e9}]
    monkeypatch.setattr(browser_mod, "sync_playwright", lambda: first)
    with BrowserMoodle(settings):
        pass
    second = FakePlaywright(installed={"chromium"})  # fresh browser: session cookies gone
    monkeypatch.setattr(browser_mod, "sync_playwright", lambda: second)
    with BrowserMoodle(settings):
        assert second.jar == [{"name": "MoodleSession", "expires": -1}]
