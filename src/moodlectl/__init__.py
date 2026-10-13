"""Moodle resources automation: Playwright SSO + optional REST web services."""

from importlib.metadata import PackageNotFoundError, version

from .browser import BrowserMoodle
from .models import ResourceSpec, Section, Resource, Course
from .rest import MoodleREST

__all__ = ["BrowserMoodle", "MoodleREST", "ResourceSpec", "Section", "Resource", "Course"]
try:
    __version__ = version("moodlectl")  # set by semantic-release in pyproject.toml
except PackageNotFoundError:  # running from an uninstalled source tree
    __version__ = "0.0.0"
