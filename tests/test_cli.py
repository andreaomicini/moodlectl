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


def test_sorted_defaults_and_errors():
    rows = [
        {"name": "b", "modified": "2026-01-02T10:00+02:00"},
        {"name": "A", "modified": None},
        {"name": "c", "modified": "2026-03-01T10:00+02:00"},
    ]
    assert [r["name"] for r in cli._sorted(rows, "name", False)] == ["A", "b", "c"]
    assert [r["name"] for r in cli._sorted(rows, "modified", False)] == ["c", "b", "A"]
    assert [r["name"] for r in cli._sorted(rows, "modified", True)] == ["b", "c", "A"]
    assert cli._sorted(rows, None, True) == rows[::-1]
    with pytest.raises(cli.moodlectlError, match="choose one of: name, modified"):
        cli._sorted(rows, "nope", False)


def test_pretty_thread_indents_replies():
    from dataclasses import asdict

    from rich.console import Console

    from moodlectl.models import Post

    def post(id, parent, message):
        when = "2026-10-01T10:00+02:00"
        return asdict(Post(id, 1, parent, f"s{id}", f"a{id}", when, when, message))

    console = Console(width=60, record=True)
    console.print(cli._thread([post(1, None, "root"), post(2, 1, "reply"), post(3, 2, "deep")]))
    lines = console.export_text().splitlines()
    indent = {m: next(ln for ln in lines if m in ln).index(m) for m in ("root", "reply", "deep")}
    assert indent["root"] < indent["reply"] < indent["deep"]
