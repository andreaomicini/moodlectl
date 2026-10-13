import tempfile
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
    "platform, order",
    [
        ("darwin", ["chrome", "chromium"]),
        ("win32", ["msedge", "chromium", "chrome"]),
        ("linux", ["firefox", "chromium", "chrome"]),
    ],
)
def test_auto_prefers_os_browser_then_falls_back(tmp_path, monkeypatch, platform, order):
    monkeypatch.setattr(browser_mod.sys, "platform", platform)
    fake = FakePlaywright(installed={order[-1]})
    monkeypatch.setattr(browser_mod, "sync_playwright", lambda: fake)
    with BrowserMoodle(_settings(tmp_path, monkeypatch, "auto")) as moodle:
        moodle._start()
        assert fake.tried == order


def test_explicit_browser_missing_reports_error(tmp_path, monkeypatch):
    fake = FakePlaywright(installed={"chromium"})
    monkeypatch.setattr(browser_mod, "sync_playwright", lambda: fake)
    with pytest.raises(moodlectlError, match="chrome"):
        with BrowserMoodle(_settings(tmp_path, monkeypatch, "chrome")) as moodle:
            moodle._start()
    assert fake.tried == ["chrome"]


def test_session_cookies_survive_restart(tmp_path, monkeypatch):
    settings = _settings(tmp_path, monkeypatch, "auto")
    first = FakePlaywright(installed={"chromium"})
    first.jar += [{"name": "MoodleSession", "expires": -1}, {"name": "kept", "expires": 2e9}]
    monkeypatch.setattr(browser_mod, "sync_playwright", lambda: first)
    with BrowserMoodle(settings) as moodle:
        moodle._start()
    second = FakePlaywright(installed={"chromium"})  # fresh browser: session cookies gone
    monkeypatch.setattr(browser_mod, "sync_playwright", lambda: second)
    with BrowserMoodle(settings) as moodle:
        moodle._start()
        assert second.jar == [{"name": "MoodleSession", "expires": -1}]


def test_page_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    settings = _settings(tmp_path, monkeypatch, "auto")
    calls = []

    def scrape(moodle, path="/x"):
        return moodle._scrape(path, lambda _p: calls.append(path) or len(calls))

    with BrowserMoodle(settings) as moodle:
        monkeypatch.setattr(moodle, "_goto", lambda path: None)
        assert scrape(moodle) == scrape(moodle) == 1  # second read is cached
        assert scrape(moodle, "/y") == 2  # cached per URL
        settings.cache_ttl = 0
        assert scrape(moodle) == 3  # --no-cache reads live, and refreshes the cache
        settings.cache_ttl = 3600
        assert scrape(moodle) == 3
        moodle._writing()
        assert scrape(moodle) == 4  # writes always read live...
    assert not settings.cache_dir.exists()  # ...and drop the cache on exit
