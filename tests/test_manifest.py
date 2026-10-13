from pathlib import Path

import pytest

from moodlectl.errors import moodlectlError
from moodlectl.manifest import load_manifest
from moodlectl.models import ResourceSpec


def test_example_manifest():
    batch = load_manifest(Path(__file__).parent.parent / "examples" / "module2.yaml")
    assert batch.course == 80509
    assert batch.section == "Module 2"
    assert len(batch.resources) == 2
    assert batch.resources[0].show_description


def test_duplicate_rejected(tmp_path):
    path = tmp_path / "manifest.yaml"
    path.write_text(
        "course: 2\nsection: 1\nresources:\n"
        ' - {kind: url, name: Test, url: "https://a.org"}\n'
        ' - {kind: url, name: test, url: "https://b.org"}\n'
    )
    with pytest.raises(moodlectlError, match="Duplicate"):
        load_manifest(path)


def test_invalid_url():
    with pytest.raises(moodlectlError, match="absolute http"):
        ResourceSpec(kind="url", name="Slides", url="javascript:alert(1)").validate()


def test_page_needs_content():
    with pytest.raises(moodlectlError, match="requires nonempty content"):
        ResourceSpec(kind="page", name="Page").validate()
