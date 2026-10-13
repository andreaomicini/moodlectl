"""Typer CLI. Run `moodlectl --help` for all commands."""
from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import asdict
from typing import Any, Optional

import typer

from .browser import BrowserMoodle
from .config import Settings, normalized_site
from .errors import moodlectlError
from .manifest import load_manifest
from .importers import import_table, write_manifest
from .models import ResourceSpec
from .rest import MoodleREST

app = typer.Typer(no_args_is_help=True, help="Moodle resources CLI (browser SSO + REST)")
courses = typer.Typer(no_args_is_help=True, help="Discover and select a course")
sections = typer.Typer(no_args_is_help=True, help="Browse course sections")
resources = typer.Typer(no_args_is_help=True, help="List, create, and update resources")
config = typer.Typer(no_args_is_help=True, help="Manage local configuration")
api = typer.Typer(no_args_is_help=True, help="Call Moodle native REST web services")
manifest = typer.Typer(no_args_is_help=True, help="Build declarative YAML manifests")
app.add_typer(courses, name="courses")
app.add_typer(sections, name="sections")
app.add_typer(resources, name="resources")
app.add_typer(config, name="config")
app.add_typer(api, name="api")
app.add_typer(manifest, name="manifest")


@app.callback()
def global_options(
    ctx: typer.Context,
    profile: str = typer.Option("default", "--profile", help="Isolated SSO browser profile"),
    site: Optional[str] = typer.Option(None, "--site", help="Moodle base URL (or MOODLE_SITE_URL)"),
):
    ctx.obj = Settings.load(profile, site)


def _settings(ctx: typer.Context) -> Settings:
    return ctx.find_root().obj


def _cid(ctx: typer.Context, provided: int | None) -> int:
    selected = provided if provided is not None else _settings(ctx).course_id
    if selected is None:
        raise moodlectlError("Select a course with `moodlectl courses use ID` or pass --course")
    return selected


@contextmanager
def browser(ctx: typer.Context):
    with BrowserMoodle(_settings(ctx)) as moodle:
        yield moodle


def _json(value: Any) -> None:
    typer.echo(json.dumps(value, indent=2, ensure_ascii=False))


@app.command()
def login(ctx: typer.Context):
    """Log in using Unibo SSO in a visible browser; keep browser profile for later commands."""
    with browser(ctx) as moodle:
        moodle.login()
    typer.echo("Authenticated Chromium profile saved locally.")


@config.command("show")
def config_show(ctx: typer.Context):
    s = _settings(ctx)
    _json({"site": s.site, "profile": s.profile,
           "course_id": s.course_id, "config_path": str(s.path),
           "browser_dir": str(s.browser_dir)})


@config.command("set-site")
def config_set_site(ctx: typer.Context, url: str):
    s = _settings(ctx)
    s.site = normalized_site(url)
    s.save()
    typer.echo(f"Moodle site: {s.site}")


@courses.command("list")
def courses_list(ctx: typer.Context, search: Optional[str] = typer.Option(None, "--search")):
    """List links from My Courses; --search searches the site course catalogue."""
    with browser(ctx) as moodle:
        _json([asdict(c) for c in moodle.list_courses(search)])


@courses.command("use")
def courses_use(ctx: typer.Context, course: int):
    """Save default course ID (does not modify Moodle)."""
    s = _settings(ctx)
    s.course_id = course
    s.save()
    typer.echo(f"Default course: {course}")


@sections.command("list")
def sections_list(ctx: typer.Context, course: Optional[int] = typer.Option(None, "--course")):
    with browser(ctx) as moodle:
        _json([{"number": x.number, "name": x.name, "section_id": x.section_id,
                "resource_count": len(x.resources)} for x in moodle.course_sections(_cid(ctx, course))])


@resources.command("list")
def resources_list(
    ctx: typer.Context,
    course: Optional[int] = typer.Option(None, "--course"),
    section: Optional[str] = typer.Option(None, "--section"),
):
    with browser(ctx) as moodle:
        _json([asdict(r) for r in moodle.list_resources(_cid(ctx, course), section)])


@resources.command("show")
def resources_show(
    ctx: typer.Context,
    cmid: int,
    course: Optional[int] = typer.Option(None, "--course"),
):
    """Show the underlying URL and edit-form metadata for a URL activity."""
    with browser(ctx) as moodle:
        _json(moodle.get_url_details(_cid(ctx, course), cmid))


@resources.command("inspect-form")
def resources_inspect_form(
    ctx: typer.Context,
    section: str = typer.Option(..., "--section"),
    course: Optional[int] = typer.Option(None, "--course"),
    kind: str = typer.Option("url", "--kind"),
):
    """List Moodle form field names, IDs and options (no write)."""
    with browser(ctx) as moodle:
        _json(moodle.inspect_form(_cid(ctx, course), section, kind=kind))


@resources.command("add-url")
def add_url(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    url: str = typer.Argument(...),
    section: str = typer.Option(..., "--section", help="Section number or title"),
    course: Optional[int] = typer.Option(None, "--course"),
    description: str = typer.Option("", "--description"),
    text_format: str = typer.Option("markdown", "--format"),
    show_description: bool = typer.Option(False, "--show-description"),
    hidden: bool = typer.Option(False, "--hidden"),
    display: Optional[str] = typer.Option(None, "--display", help="Moodle display mode label"),
    fields: str = typer.Option("{}", "--fields", help="JSON mapping extra form selectors to values"),
    if_exists: str = typer.Option("skip", "--if-exists", help="skip or error"),
):
    if if_exists not in ("skip", "error"):
        raise moodlectlError("--if-exists supports skip or error")
    spec = ResourceSpec(kind="url", name=name, url=url, description=description,
                        description_format=text_format, show_description=show_description,
                        visible=False if hidden else None, display=display,
                        fields=_parse_json_object(fields))
    with browser(ctx) as moodle:
        result = moodle.add_resource(_cid(ctx, course), section, spec, if_exists=if_exists)
    typer.echo(f"{result}: {name}")


@resources.command("add-page")
def add_page(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    content: str = typer.Option(..., "--content", help="Page body text/HTML"),
    section: str = typer.Option(..., "--section"),
    course: Optional[int] = typer.Option(None, "--course"),
    description: str = typer.Option("", "--description"),
    hidden: bool = typer.Option(False, "--hidden"),
    fields: str = typer.Option("{}", "--fields"),
):
    spec = ResourceSpec(kind="page", name=name, content=content, description=description,
                        visible=False if hidden else None, fields=_parse_json_object(fields))
    with browser(ctx) as moodle:
        result = moodle.add_resource(_cid(ctx, course), section, spec)
    typer.echo(f"{result}: {name}")


@resources.command("update-url")
def update_url(
    ctx: typer.Context,
    cmid: int,
    course: Optional[int] = typer.Option(None, "--course"),
    name: Optional[str] = typer.Option(None, "--name"),
    url: Optional[str] = typer.Option(None, "--url"),
    description: Optional[str] = typer.Option(None, "--description"),
    text_format: Optional[str] = typer.Option(None, "--format"),
    show_description: Optional[bool] = typer.Option(None, "--show-description/--hide-description"),
    visibility: Optional[bool] = typer.Option(None, "--visible/--hidden"),
    display: Optional[str] = typer.Option(None, "--display"),
    fields: str = typer.Option("{}", "--fields"),
):
    with browser(ctx) as moodle:
        moodle.update_url(_cid(ctx, course), cmid, name=name, url=url,
                          description=description, description_format=text_format,
                          show_description=show_description, visible=visibility,
                          display=display, fields=_parse_json_object(fields))
    typer.echo(f"updated: {cmid}")


def _parse_json_object(raw: str) -> dict:
    try:
        value = json.loads(raw)
    except ValueError as exc:
        raise moodlectlError(f"Invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise moodlectlError("Expected a JSON object")
    return value


@resources.command("sync")
def resources_sync(
    ctx: typer.Context,
    manifest: str = typer.Argument(..., help="YAML manifest to apply"),
    apply: bool = typer.Option(False, "--apply", help="Actually create resources (default: preview)"),
    if_exists: str = typer.Option("skip", "--if-exists", help="skip or error"),
):
    if if_exists not in ("skip", "error"):
        raise moodlectlError("--if-exists supports skip or error")
    batch = load_manifest(manifest)
    with browser(ctx) as moodle:
        sect = moodle.select_section(batch.course, batch.section)
        existing = {(r.kind, r.name.casefold()) for r in sect.resources}
        plan = [
            {"kind": spec.kind, "name": spec.name,
             "action": "exists" if (spec.kind, spec.name.casefold()) in existing else "create"}
            for spec in batch.resources
        ]
        _json({"course": batch.course, "section": sect.name, "apply": apply, "plan": plan})
        if not apply:
            typer.echo("Preview only. Re-run with --apply to create resources.")
            return
        outcomes = []
        for spec in batch.resources:
            # Re-resolve and check before every write for idempotency.
            try:
                outcome = moodle.add_resource(batch.course, sect.number, spec, if_exists=if_exists)
            except Exception:
                _json({"completed": outcomes, "failed_on": spec.name})
                raise
            outcomes.append({"resource": spec.name, "outcome": outcome})
        _json({"completed": outcomes})


@manifest.command("from-table")
def manifest_from_table(
    source_url: str = typer.Argument(..., help="Public HTML slide-table URL"),
    course: int = typer.Option(..., "--course"),
    section: str = typer.Option(..., "--section"),
    output: str = typer.Option("resources.yaml", "--output", "-o"),
):
    """Import linked PDF+online slide tables into a YAML manifest."""
    batch = import_table(source_url, course, section)
    write_manifest(batch, output)
    typer.echo(f"Wrote {len(batch.resources)} resources to {output}")


@api.command("call")
def api_call(
    ctx: typer.Context,
    function: str,
    params: str = typer.Option("{}", "--params", help="Nested JSON parameters"),
):
    """Call any provisioned Moodle REST function (requires MOODLE_WS_TOKEN)."""
    with MoodleREST(_settings(ctx).site) as ws:
        _json(ws.call(function, **_parse_json_object(params)))


@api.command("courses")
def api_courses(ctx: typer.Context):
    """List enrolled courses through native Moodle REST (requires token)."""
    with MoodleREST(_settings(ctx).site) as ws:
        _json(ws.courses())


@api.command("contents")
def api_contents(ctx: typer.Context, course: Optional[int] = typer.Option(None, "--course")):
    """Read detailed course structure through Moodle REST (requires token)."""
    with MoodleREST(_settings(ctx).site) as ws:
        _json(ws.course_contents(_cid(ctx, course)))


def main() -> None:
    try:
        app()
    except moodlectlError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)
