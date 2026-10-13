# moodlectl

A Python CLI and reusable API to inspect Moodle courses and manage learning
resources, including Moodle instances whose users authenticate using a university
SSO provider (SAML / Shibboleth / OIDC). Designed for Moodle 4.x and 5.x forms.

This is an independent utility, not an official University of Bologna/Moodle integration.

## Why two backends?

* **Browser automation (default)** uses Playwright/Chromium. You authenticate
  using the institution's real browser SSO/MFA flow; no passwords or SSO bypasses.
  This is the practical route for creating standard URL resources when REST tokens
  are not enabled or when a create-activity web service is not provisioned.
* **Moodle REST (optional)** can call external functions authorized for an existing
  Moodle web-service token. Moodle web services are configurable per installation:
  the client cannot enable them for you. `moodlepy` is a relevant library for
  this interface, but it neither solves SSO nor supplies an unrestricted
  create-activity endpoint. This project uses a tiny generic REST wrapper instead.

## Setup (macOS, Linux, Python >=3.10)

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then run:

```bash
uv sync --all-groups
uv run playwright install chromium
source .venv/bin/activate

moodlectl config set-site https://virtuale.unibo.it
moodlectl login
```

`uv sync --all-groups` creates the virtual environment and installs the project,
test tools, and development tools from `pyproject.toml`.

`login` opens a **visible, dedicated Chromium window**. Complete the normal
Unibo SSO process there, including MFA when requested. When Moodle is visible,
return to the terminal and press Enter. The persistent Chromium browser profile
is reused by subsequent commands. The tool does not ask for, save, or intercept
university passwords. Use the same `--profile` for login and later operations.

On macOS, the first run may require installing Playwright's Chromium browser.

## CLI essentials

```bash
# Read courses from your My Courses view (this view may be paginated)
moodlectl courses list

# Search the site's visible course catalogue
moodlectl courses list --search "Agenti Intelligenti"

# Set the default course for the current profile
moodlectl courses use 80509

moodlectl sections list
moodlectl resources list --section "Module 2"

# Create an URL pointing to a PDF, with visible Markdown description
moodlectl resources add-url "L2 - My lecture" \
  "https://example.org/slides.pdf" \
  --section "Module 2" \
  --description '[Online slides](https://example.org/slides/)' \
  --format markdown \
  --show-description

# Update an existing URL module by course-module ID (cmid)
moodlectl resources update-url 12345 --name "Updated title" \
  --url https://example.org/new.pdf --description '[Slides](https://example.org/)'

# Inspect the real URL field, visibility, description etc.
moodlectl resources show 12345

# See all form control selectors and select options for customization
moodlectl resources inspect-form --section "Module 2" --kind url

# Generate an actual YAML manifest from the current public APICe slide table
moodlectl manifest from-table \
  'https://apice.unibo.it/bin/view/Course/Iag2627M2/?mode=data&data=course&display=Slides' \
  --course 80509 --section "Module 2" --output module2-2026.yaml

# Batch from a YAML file: preview first, then apply
moodlectl resources sync module2-2026.yaml
moodlectl resources sync module2-2026.yaml --apply

# Provisioned native Moodle REST functions (token supplied via environment)
export MOODLE_WS_TOKEN='YOUR_PROVISIONED_TOKEN'
moodlectl api courses
moodlectl api contents --course 80509
moodlectl api call mod_url_get_urls_by_courses \
  --params '{"courseids":[80509]}'
```

Use `--profile NAME` and `--site URL` **before** the subcommand to select an
independent account or Moodle installation:

```bash
moodlectl --profile teaching --site https://virtuale.unibo.it login
moodlectl --profile teaching courses use 80509
moodlectl --profile teaching resources list --section "Module 2"
```

The saved default site/course are in
`~/.config/moodlectl/PROFILE.json` (or `$XDG_CONFIG_HOME`), and the Chromium
profile is under `~/.local/share/moodlectl/profiles/PROFILE` (or
`$XDG_DATA_HOME`). Treat the browser profile as an authenticated session.

## YAML batch files

```yaml
course: 80509
section: "Module 2"
resources:
  - kind: url
    name: "L1 - Intro"
    url: "https://example.org/l1.pdf"
    description: "[Rolling version](https://example.org/l1/)"
    description_format: markdown
    show_description: true
    visible: false
    display: "Open" # Must match a dropdown label in the site's UI; optional
    fields:
      "#id_visible": "0" # Arbitrary form fields; optional
```

`resources sync` is a **preview** unless `--apply` is provided. The batch stops
on the first form error and prints the successful operations completed so far.
Names are checked for duplicates within the selected section (kind + name):
existing resources are skipped by default, or `--if-exists error` can be used.
It does not delete or overwrite anything. `--fields` on CLI accepts the same
custom field mapping in JSON. A field key is a CSS selector; choose values
such as a string, a boolean for a checkbox, or `{label: ...}` for dropdowns.

The browser supports `url` activities as the stable, screenshot-grounded
workflow. `get_url_details` and `inspect_form` expose read-only inspection of
URL settings and arbitrary Moodle form controls; their CLI counterparts are
`resources show` and `resources inspect-form`. The generic resource creator also
accepts named module kinds (e.g. `forum` or `assign`) with site-specific required
fields provided in `fields`, but those kinds are experimental. An adapter
for Moodle `page` resources is also included; it recognizes plain textarea,
Atto contenteditable and TinyMCE iframe configurations.
`page` remains dependent on the specific site's editor configuration; test on
an expendable course first. File uploads, labels, activity deletion, complex
access restrictions and section creation are not implemented. Custom form
fields accommodate additional activity settings where Moodle exposes them.

## Programmatic Python API

```python
from moodlectl import BrowserMoodle, ResourceSpec
from moodlectl.config import Settings

with BrowserMoodle(Settings.load()) as moodle:
    for section in moodle.course_sections(80509):
        print(section.number, section.name)
        for resource in section.resources:
            print(resource.kind, resource.cmid, resource.name, resource.url)

    status = moodle.add_resource(
        80509, "Module 2",
        ResourceSpec(
            kind="url",
            name="L2 - Agents",
            url="https://example.org/l2.pdf",
            description="[Online](https://example.org/l2/)",
            description_format="markdown",
            show_description=True,
            fields={"#id_display": {"label": "Open"}},
        ),
    )
    print(status)  # 'created' or 'skipped'
```

REST usage:

```python
from moodlectl import MoodleREST

with MoodleREST("https://virtuale.unibo.it") as ws:
    print(ws.site_info())
    print(ws.course_contents(80509))
    print(ws.call("mod_url_get_urls_by_courses", courseids=[80509]))
```

## Limitations and operational notes

* **Not yet validated against an authenticated live Virtuale session**:
  the UI form/selectors match the supplied screenshots, but Virtuale plugins,
  roles, Moodle version, and updates can change selectors or permissions.
* Moodle core REST exposes course reading and module management functions,
  but resource creation is not universally exposed as a generic external
  function. A REST token must be provisioned with adequate functions/capabilities
  by the site operator; SSO cookies are not a REST `wstoken`.
* Browser course discovery is limited to course links rendered in the My Courses
  or course-search page. Explicit `--course` works even if the list is incomplete.
* The browser profile stores authenticating cookies; protect it as you would
  a web browser user profile. No SSO password is handled by this project.
* Moodle rich-text editors and course themes vary: unrecognized controls raise
  a clear `MoodleFormError` instead of silently submitting incomplete data.
* A stable independent test Moodle instance or a dedicated test course is
  recommended for live integration validation before making bulk course edits.

## Tests

```bash
uv run poe test
uv run poe static-checks
uv run poe format-check
```

Unit tests cover manifest validation, HTML table import, configuration and REST parameter
serialization. Integration against live Virtuale requires running
`moodlectl login` locally with an authorized account; no stored credentials
or Moodle tokens are included.

## Releases and dependency updates

Releases use semantic-release and Conventional Commit messages. Pushes to
`main` or `master` can publish the package to PyPI; other branches and the
initial commit run in dry-run mode. Configure `PYPI_TOKEN` and `RELEASE_TOKEN`
as repository secrets before enabling releases. `TEST_PYPI_TOKEN` is used when
the repository is a template or its name contains `template`.

Renovate is configured in `renovate.json` to open dependency update pull
requests and enable automerge after checks pass. Install the Renovate GitHub App
and enable pull request automerge in repository settings to activate it.

## References

* Moodle native web services: https://moodledev.io/docs/5.0/apis/subsystems/external
* Web service function list: https://docs.moodle.org/dev/Web_service_API_functions
* `moodlepy`: https://pypi.org/project/moodlepy/
* Playwright Python: https://playwright.dev/python/
