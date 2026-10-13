from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Literal
from urllib.parse import urlsplit

from .errors import moodlectlError

Format = Literal["markdown", "html", "plain", "auto"]


@dataclass(frozen=True)
class Course:
    id: int
    name: str
    url: str


@dataclass(frozen=True)
class Resource:
    cmid: int | None
    name: str
    kind: str
    url: str
    visible: bool | None = None


@dataclass(frozen=True)
class Section:
    number: int
    name: str
    section_id: int | None = None
    resources: tuple[Resource, ...] = ()


@dataclass(frozen=True)
class ResourceSpec:
    """Declarative Moodle activity/resource. Includes free-form UI controls.

    `fields` maps CSS selectors, `#id_field` by default, to values.
    Supported values: str/int/float for text inputs, bool for checkboxes,
    {"value": "..."} or {"label": "..."} for select options.
    """

    kind: str
    name: str
    url: str | None = None
    content: str | None = None
    description: str = ""
    description_format: Format = "markdown"
    show_description: bool = False
    visible: bool | None = None
    display: str | None = None
    fields: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if not isinstance(self.kind, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", self.kind):
            raise moodlectlError(f"Invalid Moodle module kind: {self.kind!r}")
        if self.kind == "label":
            raise moodlectlError("Label uses a different form; no label adapter is implemented")
        if not self.name.strip():
            raise moodlectlError("Resource name must not be blank")
        if self.kind == "url":
            parts = urlsplit(self.url or "")
            if parts.scheme not in {"http", "https"} or not parts.netloc:
                raise moodlectlError(f"URL resource requires an absolute http(s) URL: {self.url!r}")
        if self.kind == "page" and not self.content:
            raise moodlectlError("Page resource requires nonempty content")
        if self.description_format not in ("markdown", "html", "plain", "auto"):
            raise moodlectlError("Invalid description_format")
        if not isinstance(self.fields, dict):
            raise moodlectlError("fields must be a mapping")
