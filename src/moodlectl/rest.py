from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

import httpx

from .config import normalized_site
from .errors import moodlectlError


def flatten_moodle_params(obj: Mapping[str, Any]) -> dict[str, str]:
    """Expand a nested JSON-like value into Moodle's bracket-form parameter keys."""
    flattened: dict[str, str] = {}

    def walk(prefix: str, value: Any) -> None:
        if isinstance(value, Mapping):
            for k, v in value.items():
                walk(f"{prefix}[{k}]", v)
        elif isinstance(value, (list, tuple)):
            for idx, v in enumerate(value):
                walk(f"{prefix}[{idx}]", v)
        elif value is not None:
            flattened[prefix] = str(int(value)) if isinstance(value, bool) else str(value)

    for key, value in obj.items():
        walk(key, value)
    return flattened


class MoodleREST:
    """Token-based native Moodle REST service client (not SSO session auth)."""

    def __init__(self, site: str, token: str | None = None, timeout: float = 30):
        self.site = normalized_site(site)
        self.token = token or os.environ.get("MOODLE_WS_TOKEN")
        if not self.token:
            raise moodlectlError(
                "Set MOODLE_WS_TOKEN (requires a web-service token provisioned by Moodle)"
            )
        self.http = httpx.Client(timeout=timeout, follow_redirects=False)

    def close(self) -> None:
        self.http.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def call(self, function: str, **parameters: Any) -> Any:
        if not function.replace("_", "").isalnum():
            raise moodlectlError("Invalid Moodle web service function name")
        data = {
            "wstoken": self.token,
            "wsfunction": function,
            "moodlewsrestformat": "json",
            **flatten_moodle_params(parameters),
        }
        try:
            response = self.http.post(
                f"{self.site}/webservice/rest/server.php",
                data=data,
            )
            response.raise_for_status()
            result = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise moodlectlError(f"Moodle REST request failed: {exc}") from exc
        if isinstance(result, dict) and ("exception" in result or "errorcode" in result):
            raise moodlectlError(
                f"Moodle REST rejected {function}: {result.get('message', result)}"
            )
        return result

    def site_info(self) -> dict:
        return self.call("core_webservice_get_site_info")

    def course_contents(self, course_id: int) -> list[dict]:
        return self.call("core_course_get_contents", courseid=course_id)

    def urls(self, course_id: int) -> dict:
        return self.call("mod_url_get_urls_by_courses", courseids=[course_id])

    def courses(self) -> list[dict]:
        info = self.site_info()
        return self.call("core_enrol_get_users_courses", userid=info["userid"])
