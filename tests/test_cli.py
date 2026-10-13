import pytest
from typer.testing import CliRunner

from moodlectl import cli


class FakeMoodle:
    seen: list = []

    def __init__(self, _settings, *, headless):
        FakeMoodle.seen.append(headless)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def login(self):
        pass

    def list_forums(self, _course):
        return []


@pytest.mark.parametrize(
    "args, env, headless",
    [
        (["login"], {}, False),
        (["forums", "list", "--course", "1"], {}, True),
        (["--headless", "login"], {}, True),
        (["--headed", "forums", "list", "--course", "1"], {}, False),
        (["login"], {"MOODLE_HEADLESS": "1"}, True),
        (["forums", "list", "--course", "1"], {"MOODLE_HEADLESS": "0"}, False),
    ],
)
def test_headless_default_depends_on_command(tmp_path, monkeypatch, args, env, headless):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("MOODLE_HEADLESS", raising=False)
    monkeypatch.setattr(cli, "BrowserMoodle", FakeMoodle)
    FakeMoodle.seen = []
    result = CliRunner().invoke(cli.app, args, env=env)
    assert result.exit_code == 0, result.output
    assert FakeMoodle.seen == [headless]
