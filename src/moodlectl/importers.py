"""Generic importer for tables with a title, downloadable URL and online URL.

APICe Course/Iag2627M2's Slides view is one supported use case; the importer
requires an actual table containing the requested named columns.
"""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx
import yaml
from bs4 import BeautifulSoup

from .errors import moodlectlError
from .manifest import Batch
from .models import ResourceSpec


def parse_link_table(
    html: str,
    source_url: str,
    course: int,
    section: str | int,
    *, title_column: str = "Lecture",
    pdf_column: str = "PDF",
    online_column: str = "Online slides",
) -> Batch:
    """Extract one resource per row, PDF target + rolling Markdown link."""
    soup = BeautifulSoup(html, "html.parser")
    expected = [title_column.casefold(), pdf_column.casefold(), online_column.casefold()]
    for table in soup.select("table"):
        first_row = table.find("tr")
        if not first_row:
            continue
        header_names = [" ".join(cell.stripped_strings).casefold()
                        for cell in first_row.find_all(["th", "td"], recursive=False)]
        if not all(item in header_names for item in expected):
            continue
        index = [header_names.index(item) for item in expected]
        resources = []
        for row in table.select("tr")[1:]:
            cells = row.find_all(["td", "th"], recursive=False)
            if len(cells) <= max(index):
                continue
            title_cell, pdf_cell, online_cell = (cells[i] for i in index)
            name = " ".join(title_cell.stripped_strings)
            pdf_anchor = pdf_cell.find("a", href=True)
            online_anchor = online_cell.find("a", href=True)
            if not name or not pdf_anchor or not online_anchor:
                continue
            pdf = urljoin(source_url, pdf_anchor["href"])
            online = urljoin(source_url, online_anchor["href"])
            if any(urlsplit(url).scheme not in ("http", "https") for url in (pdf, online)):
                raise moodlectlError(f"Row {name!r}: unsupported link scheme")
            spec = ResourceSpec(
                kind="url", name=name, url=pdf,
                description=f"[Online slides (rolling)]({online})",
                description_format="markdown", show_description=True,
            )
            spec.validate()
            resources.append(spec)
        if not resources:
            raise moodlectlError("Matching table found, but no linked slide rows could be parsed")
        return Batch(course=course, section=section, resources=tuple(resources))
    raise moodlectlError(f"No HTML table found with columns: {', '.join(expected)}")


def import_table(url: str, course: int, section: str | int) -> Batch:
    if urlsplit(url).scheme != "https":
        raise moodlectlError("Import source must use HTTPS")
    try:
        with httpx.Client(timeout=45, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
            if "text/html" not in response.headers.get("content-type", "text/html"):
                raise moodlectlError("Import source did not return HTML")
            html = response.text
            final_url = str(response.url)
    except httpx.HTTPError as exc:
        raise moodlectlError(f"Cannot fetch import source: {exc}") from exc
    return parse_link_table(html, final_url, course, section)


def write_manifest(batch: Batch, output: str | Path) -> None:
    document = {
        "course": batch.course,
        "section": batch.section,
        "resources": [asdict(spec) for spec in batch.resources],
    }
    Path(output).write_text(
        yaml.safe_dump(document, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )
