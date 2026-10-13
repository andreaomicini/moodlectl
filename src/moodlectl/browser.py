from __future__ import annotations

import json
import os
import re
import sys
from contextlib import AbstractContextManager
from urllib.parse import parse_qs, urlencode, urlsplit
from getpass import getpass
from typing import Any

from playwright.sync_api import sync_playwright, Page, Locator, TimeoutError as PWTimeout
from playwright.sync_api import Error as PWError

from .config import Settings
from .errors import AmbiguousMatch, LoginRequired, moodlectlError, MoodleFormError
from .models import Course, Resource, ResourceSpec, Section


# Engines Playwright drives with its own builds; any other name is a Chromium channel
# (chromium = bundled, chrome/msedge = installed browsers, chrome-beta, ...).
OWN_ENGINES = ("firefox", "webkit")


def auto_browsers() -> tuple[str, ...]:
    """`--browser auto` order: the closest drivable match to the OS default browser
    (WebKit for Safari, installed Edge, Playwright's Firefox), then Chromium, then Chrome."""
    first = {"darwin": "webkit", "win32": "msedge"}.get(sys.platform, "firefox")
    return (first, "chromium", "chrome")


# Moodle has no universal create-URL external web-service endpoint. Use the
# supported browser form with a real lecturer SSO session instead.
SECTION_JS = r"""() => {
 const nodes = [...document.querySelectorAll('.course-section, li.section, section[id^="section-"]')];
 const used = new Set(), result = [];
 for (const node of nodes) {
   if (nodes.some(n => n !== node && node.contains(n))) continue;
   const id = node.id || '';
   const rawNumber = node.getAttribute('data-sectionnum') || id.match(/^section-(\d+)$/)?.[1];
   const h = node.querySelector('.sectionname, .section-title, h3[id^="sectionid-"], h3');
   const rawId = node.getAttribute('data-sectionid') || h?.id?.match(/^sectionid-(\d+)-/)?.[1];
   const number = rawNumber !== null && rawNumber !== undefined ? Number(rawNumber) : result.length;
   const key = rawId || id || String(number);
   if (used.has(key)) continue;
   used.add(key);
   const title = h?.querySelector('.inplaceeditable-text')?.textContent || h?.textContent || `Section ${number}`;
   const activities = node.querySelectorAll('li.activity, .activity-item');
   const seen = new Set();
   const resources = [];
   for (const el of activities) {
     if (el.matches('.activity-item') && el.closest('li.activity')) continue;
     const a = el.querySelector('.activityname a[href], a.aalink[href*="/mod/"], a[href*="/mod/"]');
     if (!a) continue;
     const href = a.href;
     const mod = href.match(/\/mod\/([a-z0-9_]+)\/view\.php/i);
     if (!mod) continue;
     const name = (a.querySelector('.instancename')?.textContent || a.textContent || '').replace(/\s+/g,' ').trim();
     const cm = (el.id || el.closest('[id^="module-"]')?.id || '').match(/module-(\d+)/);
     const cmid = cm ? Number(cm[1]) : Number(new URL(href).searchParams.get('id')) || null;
     const dup = cmid ? `id:${cmid}` : `url:${href}`;
     if (seen.has(dup)) continue;
     seen.add(dup);
     resources.push({name, kind:mod[1], url:href, cmid, visible:!el.classList.contains('dimmed')});
   }
   result.push({number, name:title.replace(/\s+/g,' ').trim(), section_id: rawId ? Number(rawId) : null, resources});
 }
 return result;
}"""


# One terminal-login step: tag visible text fields and clickable elements with
# data-moodlectl keys, and return them with the page's visible text.
STEP_JS = r"""() => {
 const vis = e => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
 const textOf = e => (e.innerText || e.value || e.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim();
 document.querySelectorAll('[data-moodlectl]').forEach(e => e.removeAttribute('data-moodlectl'));
 const tag = (e, key) => { e.setAttribute('data-moodlectl', key); return key; };
 const skip = /^(hidden|submit|button|checkbox|radio|image|reset|file)$/;
 const fields = [...document.querySelectorAll('input, textarea')]
   .filter(e => vis(e) && !e.disabled && !e.readOnly && !skip.test(e.type))
   .map((e, i) => ({key: tag(e, 'f' + i), secret: e.type === 'password',
     user: e.type === 'email' || /user|mail|login/i.test(`${e.name} ${e.id} ${e.autocomplete}`),
     label: e.labels?.[0]?.innerText.trim() || e.placeholder || e.getAttribute('aria-label') || e.name || e.type}));
 const all = [...document.querySelectorAll(
   'a[href], button, input[type=submit], input[type=button], [role=button], [onclick]')].filter(vis);
 const seen = new Set();
 const actions = all.filter(e => !all.some(o => o !== e && e.contains(o)))
   .map(e => [e, textOf(e)]).filter(([e, t]) => t && !seen.has(t) && seen.add(t))
   .map(([e, t], i) => ({key: tag(e, 'a' + i), label: t.slice(0, 80)}));
 return {text: document.body.innerText.replace(/\s+/g, ' ').trim().slice(0, 1000), fields, actions};
}"""


class BrowserMoodle(AbstractContextManager):
    """Browser-backed Moodle operations using a persistent browser SSO profile.

    Start with `with BrowserMoodle(Settings.load()) as moodle:`. The browser is
    visible so the user can complete Unibo SSO/MFA using official login pages.
    """

    def __init__(self, settings: Settings, *, headless: bool = False, timeout_ms: int = 25000):
        self.settings = settings
        self.site = settings.site
        self.headless = headless
        self.timeout_ms = timeout_ms
        self._pw = None
        self.context = None
        self.page: Page | None = None
        self._profile_dir = settings.browser_dir

    def __enter__(self):
        if self._pw is not None:
            raise moodlectlError("BrowserMoodle context is already running")
        self.settings.browser_dir.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.settings.browser_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.settings.browser_dir.chmod(0o700)
        self._pw = sync_playwright().start()
        choice = self.settings.browser
        candidates = auto_browsers() if choice == "auto" else (choice,)
        errors = []
        try:
            for name in candidates:
                # Engines cannot share a profile; Chromium channels share one.
                engine = name if name in OWN_ENGINES else "chromium"
                self._profile_dir = self.settings.browser_dir / engine
                self._profile_dir.mkdir(exist_ok=True, mode=0o700)
                try:
                    self.context = getattr(self._pw, engine).launch_persistent_context(
                        str(self._profile_dir),
                        headless=self.headless,
                        accept_downloads=True,
                        viewport={"width": 1380, "height": 960},
                        **({} if engine in OWN_ENGINES else {"channel": name}),
                    )
                    break
                except PWError as exc:
                    errors.append(f"{name}: {exc.message.strip().splitlines()[0]}")
            else:
                raise moodlectlError(
                    "No usable browser found (" + "; ".join(errors) + "). Install one with "
                    "`playwright install webkit|firefox|chromium`, or install Chrome or Edge."
                )
            if self._session_file.is_file():
                self.context.add_cookies(json.loads(self._session_file.read_text("utf-8")))
            self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
            self.page.set_default_timeout(self.timeout_ms)
        except Exception:
            self._pw.stop()
            self._pw = None
            raise
        return self

    @property
    def _session_file(self):
        return self._profile_dir / "moodlectl-session-cookies.json"

    def __exit__(self, *_):
        if self.context is not None:
            # Browsers drop session cookies (e.g. MoodleSession) on close; keep them
            # next to the profile, with the same protection, and restore on next start.
            session = [c for c in self.context.cookies() if c.get("expires", -1) == -1]
            self._session_file.write_text(json.dumps(session), "utf-8")
            os.chmod(self._session_file, 0o600)
            self.context.close()
        if self._pw is not None:
            self._pw.stop()
        self._pw = self.context = self.page = None

    def _goto(self, path: str, *, login_ok: bool = False) -> Page:
        assert self.page is not None, "Use BrowserMoodle inside a with block"
        self.page.goto(f"{self.site}{path}", wait_until="domcontentloaded")
        if not login_ok:
            self._require_login()
        return self.page

    def _require_login(self) -> None:
        assert self.page is not None
        url = urlsplit(self.page.url)
        # SAML/OIDC systems may redirect to an entirely different domain.
        site_path = urlsplit(self.site).path.rstrip("/")
        if url.netloc != urlsplit(self.site).netloc or url.path.startswith(
            (site_path + "/login/", site_path + "/auth/")
        ):
            raise LoginRequired(
                "Moodle redirected to login/SSO. Run `moodlectl login` interactively "
                "using the same --profile and --site."
            )
        if self.page.locator('form#login, input[name="password"]').count():
            raise LoginRequired("Moodle login form displayed; run `moodlectl login` first")

    def login(self) -> None:
        """Interactive SSO in the visible browser, or step by step in the terminal if headless."""
        self._goto("/my/courses.php", login_ok=True)
        if self.headless:
            self._terminal_login()
        else:
            print("Complete the University's SSO/MFA login in the opened browser window.")
            input("When the authenticated Moodle page is visible, press Enter here: ")
        # Recheck a protected route; do not persist passwords or request tokens.
        p = self._goto("/my/courses.php")
        if p.locator("body.notloggedin, #page-login-index").count():
            raise LoginRequired("Moodle does not report an authenticated account")

    def _terminal_login(self) -> None:
        """Walk the SSO pages headlessly: show each page's text, prompt for its fields,
        and let the user pick what to click. Passwords are read with getpass and only
        typed into the page; they are never printed or stored.
        """
        # ponytail: main frame only; add frame traversal if an IdP puts its form in an iframe.
        try:
            self._terminal_login_steps()
        except EOFError:
            raise LoginRequired("Login aborted: no more terminal input") from None

    def _terminal_login_steps(self) -> None:
        p = self.page
        assert p is not None
        while True:
            try:
                self._require_login()
                return
            except LoginRequired:
                pass
            step = p.evaluate(STEP_JS)
            fields, actions = step["fields"], step["actions"]
            print(f"\n--- {p.title() or urlsplit(p.url).netloc} ---\n{step['text']}\n")
            for field in fields:
                env = "MOODLE_PASSWORD" if field["secret"] else "MOODLE_USERNAME"
                value = os.environ.get(env) if field["secret"] or field["user"] else None
                if value:
                    print(f"{field['label']}: (from {env})")
                else:
                    value = (getpass if field["secret"] else input)(f"{field['label']}: ")
                if value:
                    p.locator(f'[data-moodlectl="{field["key"]}"]').fill(value)
            for i, action in enumerate(actions, 1):
                print(f"  {i}) {action['label']}")
            default = "submit" if fields else "wait for the page to change"
            while True:
                choice = input(f"Choose 1-{len(actions)}, Enter = {default}, q = quit: ").strip()
                if choice == "q":
                    raise LoginRequired("Login aborted")
                if choice == "" or (choice.isdigit() and 1 <= int(choice) <= len(actions)):
                    break
            if choice:
                p.locator(f'[data-moodlectl="{actions[int(choice) - 1]["key"]}"]').click()
            elif fields:
                p.locator(f'[data-moodlectl="{fields[-1]["key"]}"]').press("Enter")
            p.wait_for_timeout(1500)
            try:
                p.wait_for_load_state("networkidle", timeout=self.timeout_ms)
            except PWTimeout:
                pass

    def list_courses(self, search: str | None = None) -> list[Course]:
        path = (
            "/course/search.php?" + urlencode({"search": search}) if search else "/my/courses.php"
        )
        p = self._goto(path)
        raw = p.eval_on_selector_all(
            'a[href*="/course/view.php?id="]',
            """els => els.map(a => ({name:(a.textContent||'').trim(), url:a.href}))""",
        )
        courses: dict[int, Course] = {}
        for item in raw:
            parsed = urlsplit(item["url"])
            if parsed.netloc != urlsplit(self.site).netloc:
                continue
            ids = parse_qs(parsed.query).get("id", [])
            if not ids or not ids[0].isdigit():
                continue
            cid = int(ids[0])
            if cid not in courses or len(item["name"]) > len(courses[cid].name):
                courses[cid] = Course(cid, item["name"] or str(cid), item["url"])
        result = sorted(courses.values(), key=lambda c: c.name.casefold())
        return [c for c in result if not search or search.casefold() in c.name.casefold()]

    def course_sections(self, course_id: int) -> list[Section]:
        p = self._goto(f"/course/view.php?id={int(course_id)}")
        raw: list[dict] = p.evaluate(SECTION_JS)
        if not raw:
            raise moodlectlError("Cannot find Moodle course sections; check course access/layout")
        return [
            Section(
                number=s["number"],
                name=s["name"],
                section_id=s["section_id"],
                resources=tuple(Resource(**r) for r in s["resources"]),
            )
            for s in raw
        ]

    def select_section(self, course_id: int, selector: str | int) -> Section:
        sections = self.course_sections(course_id)
        if isinstance(selector, int) or (isinstance(selector, str) and selector.isdigit()):
            hits = [s for s in sections if s.number == int(selector)]
        else:
            exact = [s for s in sections if s.name.casefold() == str(selector).casefold()]
            hits = exact or [s for s in sections if str(selector).casefold() in s.name.casefold()]
        if not hits:
            raise moodlectlError(
                f"Section {selector!r} not found in course {course_id}. "
                f"Available: {[(s.number, s.name) for s in sections]}"
            )
        if len(hits) > 1:
            raise AmbiguousMatch(f"Section selector {selector!r} matched multiple sections")
        return hits[0]

    def list_resources(self, course_id: int, section: str | int | None = None) -> list[Resource]:
        if section is not None:
            return list(self.select_section(course_id, section).resources)
        return [
            resource
            for section in self.course_sections(course_id)
            for resource in section.resources
        ]

    def _edit_form(
        self,
        *,
        course_id: int | None = None,
        section_no: int | None = None,
        kind: str = "url",
        cmid: int | None = None,
    ) -> Page:
        if cmid is not None:
            path = "/course/modedit.php?" + urlencode({"update": cmid, "return": 0})
        else:
            if course_id is None or section_no is None:
                raise moodlectlError("course_id and section_no required for creation")
            path = "/course/modedit.php?" + urlencode(
                {
                    "add": kind,
                    "course": course_id,
                    "section": section_no,
                    "return": 0,
                    "beforemod": 0,
                }
            )
            # Moodle's `type` parameter is optional; choose generic module type.
        p = self._goto(path)
        if not p.locator("form#mform1, form:has(#id_name)").count():
            raise MoodleFormError(f"Moodle did not display the {kind} edit form: {p.url}")
        return p

    @staticmethod
    def _locate(p: Page, selectors: str) -> Locator:
        for selector in selectors.split(" || "):
            loc = p.locator(selector).first
            if loc.count():
                return loc
        raise MoodleFormError(f"Required field missing: {selectors}")

    @staticmethod
    def _optional(p: Page, selector: str) -> Locator | None:
        loc = p.locator(selector).first
        return loc if loc.count() else None

    @staticmethod
    def _select_format(p: Page, selector: str, fmt: str) -> None:
        loc = BrowserMoodle._optional(p, selector)
        if loc is None:
            if fmt != "auto":
                raise MoodleFormError(f"Formatting selector missing: {selector}")
            return
        # Standard Moodle FORMAT_* constants: 0=Moodle, 1=HTML, 2=plain, 4=Markdown.
        format_values = {"auto": "0", "html": "1", "plain": "2", "markdown": "4"}
        if fmt not in format_values:
            raise moodlectlError(f"Invalid description format: {fmt!r}")
        value = format_values[fmt]
        if value not in loc.locator("option").evaluate_all("els => els.map(e => e.value)"):
            raise MoodleFormError(f"Formatting type {fmt} not offered by this Moodle form")
        loc.select_option(value=value)

    @staticmethod
    def _fill_field(p: Page, selector: str, value: Any) -> None:
        """Apply a declared custom UI control. Errors are explicit, never skipped."""
        loc = BrowserMoodle._locate(p, selector)
        tag = loc.evaluate("el => el.tagName.toLowerCase()")
        typ = loc.get_attribute("type")
        if tag == "select":
            if isinstance(value, dict):
                if "label" in value:
                    loc.select_option(label=str(value["label"]))
                elif "value" in value:
                    loc.select_option(value=str(value["value"]))
                else:
                    raise MoodleFormError(f"Selector {selector}: expected label or value")
            else:
                loc.select_option(value=str(value))
        elif typ in ("checkbox", "radio"):
            loc.check() if bool(value) else loc.uncheck()
        elif tag in ("input", "textarea"):
            loc.fill(str(value))
        else:
            raise MoodleFormError(f"Unsupported field widget: {selector} ({tag})")

    def _fill_rich_text(self, p: Page, field: str, text: str) -> None:
        # Support native textarea and common Atto/TinyMCE editor widgets.
        wrappers = [
            f'#fitem_id_{field} [contenteditable="true"]',
            f'#{field}editable[contenteditable="true"]',
        ]
        for selector in wrappers:
            loc = self._optional(p, selector)
            if loc and loc.is_visible():
                loc.fill(text)
                return
        selector = f'textarea#id_{field}, textarea[name="{field}[text]"]'
        loc = self._optional(p, selector)
        if loc and loc.is_visible():
            loc.fill(text)
            return
        # TinyMCE within editor iframe; scope to form component.
        frames = p.frame_locator(f"#fitem_id_{field} iframe").locator(
            'body[contenteditable="true"]'
        )
        if frames.count():
            frames.first.fill(text)
            return
        if loc:
            # An editor plugin may have kept the textarea hidden. Do not replace
            # its value behind the editor; doing so would risk saving stale text.
            raise MoodleFormError(
                f"Rich text editor for '{field}' is not recognized. "
                "Use a form-specific adapter via extra fields."
            )
        raise MoodleFormError(f"Content field '{field}' not found")

    def _populate(self, p: Page, spec: ResourceSpec, *, updating: bool = False) -> None:
        spec.validate()
        expand = p.get_by_text(re.compile(r"^(Expand all|Espandi tutto)$", re.I)).first
        if expand.count() and expand.is_visible():
            expand.click()
        self._locate(p, "#id_name").fill(spec.name)
        if spec.kind == "url":
            self._locate(p, "#id_externalurl").fill(spec.url or "")
        if spec.description:
            self._select_format(p, "#menuintroeditorformat", spec.description_format)
            desc = self._locate(p, "#id_introeditor")
            desc.fill(spec.description)
        elif not updating:
            blank = self._optional(p, "#id_introeditor")
            if blank and blank.is_visible():
                blank.fill("")
        show = self._optional(p, '#id_showdescription, input[name="showdescription"]')
        if show is not None:
            show.check() if spec.show_description else show.uncheck()
        elif spec.show_description:
            raise MoodleFormError("Moodle form lacks show-description checkbox")
        if spec.visible is not None:
            self._fill_field(p, "#id_visible", "1" if spec.visible else "0")
        if spec.display is not None:
            self._fill_field(p, "#id_display", {"label": spec.display})
        if spec.kind == "page":
            self._fill_rich_text(p, "page", spec.content or "")
        for selector, value in spec.fields.items():
            self._fill_field(p, selector, value)

    def _save(self, p: Page) -> None:
        button = self._locate(
            p, '#id_submitbutton2 || input[name="submitbutton2"] || #id_submitbutton'
        )
        button.click()
        try:
            p.wait_for_load_state("domcontentloaded", timeout=self.timeout_ms)
        except PWTimeout as exc:
            raise MoodleFormError("Timed out waiting for Moodle to save") from exc
        if "/course/modedit.php" in p.url:
            errors = p.locator(
                '.invalid-feedback, .error, .alert-danger, [role="alert"]'
            ).all_text_contents()
            raise MoodleFormError(
                "Moodle did not leave the editing form. Validation errors: "
                + (" | ".join(dict.fromkeys(e.strip() for e in errors if e.strip())) or "unknown")
            )
        if urlsplit(p.url).netloc != urlsplit(self.site).netloc:
            raise MoodleFormError(f"Unexpected post-save navigation: {p.url}")

    def add_resource(
        self, course_id: int, section: str | int, spec: ResourceSpec, *, if_exists: str = "skip"
    ) -> str:
        """Create one resource; skip or error if its name+kind already exists.

        Section resolution and duplicate detection re-read the current course.
        Return 'created' or 'skipped'. No destructive overwrite occurs.
        """
        spec.validate()
        target = self.select_section(course_id, section)
        existing = [
            r
            for r in target.resources
            if r.name.casefold() == spec.name.casefold() and r.kind == spec.kind
        ]
        if existing:
            if if_exists == "skip":
                return "skipped"
            raise moodlectlError(f"Resource already exists in section {target.name}: {spec.name}")
        p = self._edit_form(course_id=course_id, section_no=target.number, kind=spec.kind)
        self._populate(p, spec)
        self._save(p)
        refreshed = self.select_section(course_id, target.number)
        if not any(
            r.name.casefold() == spec.name.casefold() and r.kind == spec.kind
            for r in refreshed.resources
        ):
            raise MoodleFormError(
                f"Save returned but {spec.name!r} was not found in section {target.name}. "
                "Inspect the course before retrying."
            )
        return "created"

    def inspect_form(self, course_id: int, section: str | int, *, kind: str = "url") -> list[dict]:
        """Inspect actual Moodle input/select/textarea controls without submitting."""
        target = self.select_section(course_id, section)
        p = self._edit_form(course_id=course_id, section_no=target.number, kind=kind)
        return p.locator(
            "form#mform1 input, form#mform1 select, form#mform1 textarea"
        ).evaluate_all(
            """els => els.filter(e => e.name || e.id).map(e => ({
              id:e.id, name:e.name, type:e.type,
              options:e.tagName==='SELECT' ? [...e.options].map(o => ({value:o.value,label:o.textContent.trim()})) : null,
              checked:e.type==='checkbox' ? e.checked : null
            }))"""
        )

    def get_url_details(self, course_id: int, cmid: int) -> dict:
        """Read the destination/description from a URL's edit form (teacher role)."""
        resources = [
            r for r in self.list_resources(course_id) if r.cmid == cmid and r.kind == "url"
        ]
        if len(resources) != 1:
            raise moodlectlError(f"URL cmid={cmid} not found in course {course_id}")
        p = self._edit_form(cmid=cmid)
        desc = self._optional(p, "#id_introeditor")
        fmt = self._optional(p, "#menuintroeditorformat")
        show = self._optional(p, '#id_showdescription, input[name="showdescription"]')
        visible = self._optional(p, "#id_visible")
        display = self._optional(p, "#id_display")
        return {
            "cmid": cmid,
            "course": course_id,
            "name": self._locate(p, "#id_name").input_value(),
            "url": self._locate(p, "#id_externalurl").input_value(),
            "description": desc.input_value() if desc else None,
            "description_format_value": fmt.input_value() if fmt else None,
            "show_description": show.is_checked() if show else None,
            "visible_value": visible.input_value() if visible else None,
            "display_value": display.input_value() if display else None,
        }

    def update_url(
        self,
        course_id: int,
        cmid: int,
        *,
        name: str | None = None,
        url: str | None = None,
        description: str | None = None,
        description_format: str | None = None,
        show_description: bool | None = None,
        visible: bool | None = None,
        display: str | None = None,
        fields: dict | None = None,
    ) -> None:
        """Update a URL activity using only the fields explicitly supplied."""
        existing = [r for r in self.list_resources(course_id) if r.cmid == cmid and r.kind == "url"]
        if len(existing) != 1:
            raise moodlectlError(f"URL activity cmid={cmid} not found in course {course_id}")
        if url is not None:
            ResourceSpec(kind="url", name=name or existing[0].name, url=url).validate()
        p = self._edit_form(cmid=cmid)
        if name is not None:
            if not name.strip():
                raise moodlectlError("Updated name cannot be blank")
            self._locate(p, "#id_name").fill(name)
        if url is not None:
            self._locate(p, "#id_externalurl").fill(url)
        if description is not None or description_format is not None:
            if description_format:
                self._select_format(p, "#menuintroeditorformat", description_format)
            if description is not None:
                self._locate(p, "#id_introeditor").fill(description)
        if show_description is not None:
            checkbox = self._locate(p, '#id_showdescription || input[name="showdescription"]')
            checkbox.check() if show_description else checkbox.uncheck()
        if visible is not None:
            self._fill_field(p, "#id_visible", "1" if visible else "0")
        if display is not None:
            self._fill_field(p, "#id_display", {"label": display})
        for selector, value in (fields or {}).items():
            self._fill_field(p, selector, value)
        self._save(p)
        if not any(r.cmid == cmid for r in self.list_resources(course_id)):
            raise MoodleFormError(f"Resource cmid={cmid} missing after edit; inspect manually")
