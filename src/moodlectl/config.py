from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from .errors import moodlectlError


def _xdg_dir(env_name: str, fallback: str) -> Path:
    return Path(os.environ.get(env_name, Path.home() / fallback)).expanduser()


def normalized_site(site: str) -> str:
    site = site.strip().rstrip("/")
    parts = urlsplit(site)
    if parts.scheme not in ("https", "http") or not parts.hostname:
        raise moodlectlError("Site must be an absolute http(s) URL")
    if parts.scheme == "http" and parts.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise moodlectlError("HTTP is allowed only for localhost; use HTTPS")
    if parts.query or parts.fragment or parts.username or parts.password:
        raise moodlectlError("Site URL must not contain query, fragment or credentials")
    return site


@dataclass
class Settings:
    profile: str = "default"
    site: str = "https://virtuale.unibo.it"
    course_id: int | None = None

    @property
    def path(self) -> Path:
        return _xdg_dir("XDG_CONFIG_HOME", ".config") / "moodlectl" / f"{self.profile}.json"

    @property
    def browser_dir(self) -> Path:
        # Dedicated Chromium user-data dir; no cookie/token export or parsing.
        return _xdg_dir("XDG_DATA_HOME", ".local/share") / "moodlectl" / "profiles" / self.profile

    @classmethod
    def load(cls, profile: str = "default", site: str | None = None) -> "Settings":
        if not re.fullmatch(r"[A-Za-z0-9_-]+", profile):
            raise moodlectlError("Profile must contain only letters, digits, underscore or hyphen")
        settings = cls(profile=profile)
        if settings.path.is_file():
            data = json.loads(settings.path.read_text(encoding="utf-8"))
            settings.site = normalized_site(data.get("site", settings.site))
            course_id = data.get("course_id")
            settings.course_id = int(course_id) if course_id is not None else None
        settings.site = normalized_site(site or os.getenv("MOODLE_SITE_URL") or settings.site)
        return settings

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.path.parent, 0o700)
        self.path.write_text(
            json.dumps({"site": self.site, "course_id": self.course_id}, indent=2) + "\n",
            encoding="utf-8",
        )
        os.chmod(self.path, 0o600)
