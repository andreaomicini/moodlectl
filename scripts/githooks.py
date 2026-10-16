"""Install or remove this repo's local Git hooks (never tracked: they live in .git/hooks).

python scripts/githooks.py install|uninstall [HOOK...]   # default: all hooks
python scripts/githooks.py check-msg FILE                # used by commit-msg
"""

from __future__ import annotations

import re
import stat
import subprocess
import sys
from pathlib import Path

MARKER = "# moodlectl-githook"
HOOKS = {
    "pre-commit": "exec uv run poe static-checks",
    "commit-msg": 'exec uv run python scripts/githooks.py check-msg "$1"',
    "pre-push": "uv run poe static-checks && exec uv run poe test",
}
TYPES = "build|chore|ci|docs|feat|fix|perf|refactor|revert|style|test"
CONVENTIONAL = re.compile(rf"^({TYPES})(\([^()\s][^()]*\))?!?: \S")
# Messages git writes itself (merges, reverts, autosquash) are let through.
EXEMPT = re.compile(r"^(Merge |Revert \"|fixup! |squash! |amend! )")
# AI assistants' trailers and footers; a plain mention of a tool in the text is fine.
AI = r"claude|anthropic|codex|openai|chatgpt|gpt-?\d|copilot|gemini|cursor|aider|devin"
AI_SIGNATURE = re.compile(
    rf"^\s*(co-authored-by|signed-off-by|assisted-by|generated-by):.*\b({AI})\b"
    rf"|generated (with|by)\b.*\b({AI})\b"
    r"|noreply@(anthropic|openai)\.com",
    re.IGNORECASE,
)
SCISSORS = "# ------------------------ >8 ------------------------"


def hooks_dir() -> Path:
    out = subprocess.run(
        ["git", "rev-parse", "--git-path", "hooks"], check=True, capture_output=True, text=True
    )
    return Path(out.stdout.strip())


def is_ours(path: Path) -> bool:
    return path.exists() and MARKER in path.read_text(encoding="utf-8", errors="replace")


def install(names: list[str]) -> int:
    folder = hooks_dir()
    folder.mkdir(parents=True, exist_ok=True)
    failed = 0
    for name in names:
        path = folder / name
        if path.exists() and not is_ours(path):
            print(f"{name}: skipped, {path} exists and was not installed by this script")
            failed = 1
            continue
        path.write_text(f"#!/bin/sh\n{MARKER}\n{HOOKS[name]}\n", encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        print(f"{name}: installed")
    return failed


def uninstall(names: list[str]) -> int:
    folder = hooks_dir()
    for name in names:
        path = folder / name
        if is_ours(path):
            path.unlink()
            print(f"{name}: removed")
        elif path.exists():
            print(f"{name}: not installed by this script, left alone")
        else:
            print(f"{name}: not installed")
    return 0


def check_msg(file: str) -> int:
    text = Path(file).read_text(encoding="utf-8").split(SCISSORS)[0]  # drop `commit -v` diff
    lines = [s for s in text.splitlines() if not s.startswith("#")]
    signed = [s for s in lines if AI_SIGNATURE.search(s)]
    if signed:
        print(
            "commit-msg: remove the AI assistant signature:", *signed, sep="\n  ", file=sys.stderr
        )
        return 1
    subject = next((s for s in lines if s.strip()), "")
    if CONVENTIONAL.match(subject) or EXEMPT.match(subject):
        return 0
    print(
        f"commit-msg: not a Conventional Commit: {subject!r}\n"
        f"expected '<type>[(scope)][!]: <description>', type one of {TYPES.replace('|', ', ')}",
        file=sys.stderr,
    )
    return 1


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[0] == "check-msg":
        return check_msg(argv[1])
    if not argv or argv[0] not in ("install", "uninstall"):
        print(__doc__, file=sys.stderr)
        return 2
    names = argv[1:] or list(HOOKS)
    unknown = sorted(set(names) - set(HOOKS))
    if unknown:
        print(f"unknown hooks: {', '.join(unknown)}; available: {', '.join(HOOKS)}")
        return 2
    return (install if argv[0] == "install" else uninstall)(names)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
