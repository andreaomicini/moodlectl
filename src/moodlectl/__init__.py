"""Moodle resources automation: Playwright SSO + optional REST web services."""

from importlib.metadata import PackageNotFoundError, version

from .browser import BrowserMoodle
from .models import Course, Discussion, Post, Resource, ResourceSpec, Section
from .rest import MoodleREST

__all__ = [
    "BrowserMoodle",
    "MoodleREST",
    "ResourceSpec",
    "Section",
    "Resource",
    "Course",
    "Discussion",
    "Post",
]
try:
    __version__ = version("moodlectl")  # set by semantic-release in pyproject.toml
except PackageNotFoundError:  # running from an uninstalled source tree
    __version__ = "0.0.0"
