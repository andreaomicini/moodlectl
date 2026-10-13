import pytest

from moodlectl.errors import moodlectlError
from moodlectl.importers import parse_link_table, write_manifest
from moodlectl.manifest import load_manifest

HTML = """
<table><thead><tr><th>Lecture</th><th>PDF</th><th>Online slides</th></tr></thead>
<tbody><tr><td>0. About the course</td><td><a href="https://example.org/0.pdf">Download PDF</a></td>
<td><a href="https://example.org/0/">Open slides</a></td></tr>
<tr><td>1. Intro</td><td><a href="1.pdf">Download PDF</a></td>
<td><a href="/slides/intro/">Open slides</a></td></tr></tbody></table>
"""


def test_parse_realistic_table(tmp_path):
    batch = parse_link_table(HTML, "https://apice.example.edu/course", 80509, "Module 2")
    assert len(batch.resources) == 2
    assert batch.resources[0].url == "https://example.org/0.pdf"
    assert batch.resources[0].show_description is True
    assert batch.resources[1].url == "https://apice.example.edu/1.pdf"
    target = tmp_path / "batch.yaml"
    write_manifest(batch, target)
    assert load_manifest(target) == batch


def test_bad_header():
    with pytest.raises(moodlectlError, match="No HTML table"):
        parse_link_table("<table><tr><th>A</th></tr></table>", "https://a.org", 5, 1)
