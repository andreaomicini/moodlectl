"""Opt-in live SSO login test against a real Moodle, once per browser.

Run with: MOODLE_LIVE_TEST=1 MOODLE_USERNAME=... MOODLE_PASSWORD=... uv run poe test-live
Optional: MOODLE_SITE_URL, MOODLE_LIVE_BROWSERS (default: webkit,firefox,chromium,chrome).
Prompts (button choices, MFA codes) are answered on the terminal, hence `pytest -s`.
"""

import os

import pytest

from moodlectl.browser import BrowserMoodle
from moodlectl.config import Settings

BROWSERS = os.environ.get("MOODLE_LIVE_BROWSERS", "webkit,firefox,chromium,chrome").split(",")

pytestmark = pytest.mark.skipif(
    not (os.environ.get("MOODLE_LIVE_TEST") and os.environ.get("MOODLE_PASSWORD")),
    reason="set MOODLE_LIVE_TEST=1, MOODLE_USERNAME and MOODLE_PASSWORD to run",
)


@pytest.mark.parametrize("browser", BROWSERS)
def test_headless_login_persists(tmp_path, monkeypatch, browser):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))  # fresh, throwaway profile
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    settings = Settings.load("live")
    settings.browser = browser
    print(f"\n===== {browser} =====")
    with BrowserMoodle(settings, headless=True) as moodle:
        moodle.login()
    with BrowserMoodle(settings, headless=True) as moodle:  # new process state, same profile
        print(f"{browser}: {len(moodle.list_courses())} courses visible after restart")
