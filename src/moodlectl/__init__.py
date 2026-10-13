"""Moodle resources automation: Playwright SSO + optional REST web services."""
from .browser import BrowserMoodle
from .models import ResourceSpec, Section, Resource, Course
from .rest import MoodleREST

__all__ = ["BrowserMoodle", "MoodleREST", "ResourceSpec", "Section", "Resource", "Course"]
__version__ = "0.1.0"
