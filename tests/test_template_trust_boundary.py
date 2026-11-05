"""Tripwires for the overlay template trust boundary (AUTHENTICATION.md §2.5.1).

Overlay templates and scripts run on the app's origin with the viewing
owner's session, so they are trusted code. These tests pin the three rules
that keep it that way: templates only come from the deployed catalog,
operator data never reaches an HTML sink, and uploads stay inert.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "overlay_templates"
OVERLAY_JS = ROOT / "overlay_static" / "js"

# Rule 2 — operator data reaches pages only as escaped text.
_TEMPLATE_ESCAPE_BYPASSES = re.compile(r"\|\s*safe\b|autoescape\s+false|Markup\b")
_JS_HTML_SINKS = re.compile(
    r"\b(innerHTML|outerHTML|srcdoc)\b"
    r"|insertAdjacentHTML|createContextualFragment|DOMParser"
    r"|document\.write"
    r"|\beval\s*\(|\bnew\s+Function\b"
    r"|setAttribute\(\s*[\"']on"
)
_JINJA_EXPR = re.compile(r"\{\{(.*?)\}\}", re.S)
# Values the server constrains before rendering (AUTHENTICATION.md §2.5.1):
# the output token, a catalog style, the native theme, a supported locale.
_SCRIPT_SAFE_VARIABLES = {"output_key", "target_id", "style", "native_theme", "locale"}


class _InlineScripts(HTMLParser):
    """Collect the text of every inline ``<script>`` element.

    Uses the stdlib HTML tokenizer rather than a regex so every end-tag
    form (``</script >``, ``</SCRIPT\n>``, …) closes the element exactly as
    a browser would.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.bodies: list[str] = []
        self._current: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "script":
            self._current = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._current is not None:
            self.bodies.append("".join(self._current))
            self._current = None

    def handle_data(self, data: str) -> None:
        if self._current is not None:
            self._current.append(data)


def _inline_scripts(html: str) -> list[str]:
    parser = _InlineScripts()
    parser.feed(html)
    parser.close()
    return parser.bodies


def _strip_js_comments(source: str) -> str:
    """Drop // and /* */ comments so prose about a sink is not a sink."""
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    return re.sub(r"(^|[^:\\])//[^\n]*", r"\1", source)


def _overlay_scripts() -> list[Path]:
    return sorted(p for p in OVERLAY_JS.glob("*.js") if not p.name.endswith(".min.js"))


def _templates() -> list[Path]:
    return sorted(TEMPLATES.glob("*.html"))


@pytest.mark.parametrize("path", _templates(), ids=lambda p: p.name)
def test_templates_never_bypass_autoescaping(path):
    hits = _TEMPLATE_ESCAPE_BYPASSES.findall(path.read_text(encoding="utf-8"))
    assert not hits, f"{path.name} bypasses Jinja autoescaping: {hits}"


def test_app_never_marks_markup_safe():
    for path in (ROOT / "app").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert not re.search(r"\bimport\b.*\bMarkup\b|\bMarkup\s*\(", source), path


@pytest.mark.parametrize("path", _overlay_scripts(), ids=lambda p: p.name)
def test_overlay_scripts_write_text_not_html(path):
    source = _strip_js_comments(path.read_text(encoding="utf-8"))
    hits = [m.group(0) for m in _JS_HTML_SINKS.finditer(source)]
    assert not hits, (
        f"{path.name} uses an HTML/code sink ({hits}); use textContent / createElement — "
        "operator-controlled strings reach these pages (AUTHENTICATION.md §2.5.1)"
    )


@pytest.mark.parametrize("path", _templates(), ids=lambda p: p.name)
def test_inline_scripts_have_no_sinks_and_only_constrained_values(path):
    """Jinja escapes HTML, not JS string context: inside <script> only
    server-constrained variables or ``|tojson`` may be interpolated."""
    bodies = _inline_scripts(path.read_text(encoding="utf-8"))
    for body in bodies:
        code = _strip_js_comments(body)
        assert not _JS_HTML_SINKS.search(code), (path.name, _JS_HTML_SINKS.search(code))
        for expr in _JINJA_EXPR.findall(body):
            expr = expr.strip()
            if re.search(r"\|\s*tojson\b", expr):
                continue
            name = re.split(r"[|\s.(\[]", expr, maxsplit=1)[0]
            assert name in _SCRIPT_SAFE_VARIABLES, (
                f"{path.name} interpolates {{{{ {expr} }}}} into a script; "
                "use |tojson or a server-constrained value"
            )


def test_overlay_jinja_environment_autoescapes_html():
    from fastapi.templating import Jinja2Templates

    from app.bootstrap import OVERLAY_TEMPLATES_DIR

    env = Jinja2Templates(directory=str(OVERLAY_TEMPLATES_DIR)).env
    autoescape = env.autoescape
    assert autoescape("index.html") if callable(autoescape) else autoescape


# Rule 1 — templates come only from the deployed catalog.


def test_no_route_writes_to_overlay_or_static_surfaces(app_client):
    """Nothing under the overlay/static mounts accepts a request body."""
    from starlette.routing import Mount, Route, WebSocketRoute

    surfaces = ("/overlay", "/overlay-preview", "/follow", "/ws/", "/static", "/fonts", "/media")
    for route in app_client.app.routes:
        path = getattr(route, "path", "")
        if not path.startswith(surfaces):
            continue
        if isinstance(route, Route):
            assert set(route.methods or ()) <= {"GET", "HEAD"}, (path, route.methods)
        else:
            assert isinstance(route, (Mount, WebSocketRoute)), (path, route)


def test_no_api_route_takes_template_content(app_client):
    """No API endpoint is about templates/scripts — a deliberate absence."""
    from starlette.routing import Route

    for route in app_client.app.routes:
        if not isinstance(route, Route) or not set(route.methods or ()) - {"GET", "HEAD"}:
            continue
        assert not re.search(r"template|script|/js\b", route.path, re.I), route.path


def test_persisted_style_outside_the_catalog_falls_back_to_default(auth_client):
    from app.overlay import overlay_state_store

    auth_client.post("/api/v1/session/init", json={"oid": "trust-style"})
    overlay = next(
        o for o in auth_client.get("/api/v1/overlays").json() if o["oid"] == "trust-style"
    )
    skey = f"{auth_client.test_user_id}:trust-style"
    overlay_state_store.set_raw_config(
        skey, customization={"preferredStyle": "../../app/bootstrap"},
    )
    res = auth_client.get(f"/overlay/{overlay['public_token']}")
    assert res.status_code == 200
    assert 'window.OVERLAY_STYLE = "default";' in res.text
    assert "bootstrap" not in res.text.split("window.OVERLAY_STYLE", 1)[1][:40]


@pytest.mark.parametrize(
    "style", ["../base", "../../app/bootstrap", "base/../index", "_spectator", "nonexistent"],
)
def test_style_query_outside_the_catalog_is_404(auth_client, style):
    auth_client.post("/api/v1/session/init", json={"oid": "trust-query"})
    overlay = next(
        o for o in auth_client.get("/api/v1/overlays").json() if o["oid"] == "trust-query"
    )
    res = auth_client.get(f"/overlay/{overlay['public_token']}", params={"style": style})
    assert res.status_code == 404


# Rule 3 — uploads stay inert.


@pytest.mark.parametrize(
    "payload",
    [
        b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
        b"<!doctype html><script>alert(1)</script>",
    ],
    ids=["svg", "html"],
)
def test_icon_upload_rejects_markup(payload):
    from app.icons_service import IconError, process_icon_upload

    with pytest.raises(IconError):
        process_icon_upload(payload)


def test_icon_upload_is_reencoded_so_trailing_markup_is_dropped():
    """A real image carrying an HTML tail comes out as plain WebP bytes."""
    import io

    from PIL import Image

    from app.icons_service import process_icon_upload

    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (200, 30, 30)).save(buf, format="PNG")
    polyglot = buf.getvalue() + b"<script>alert(1)</script>"
    out = process_icon_upload(polyglot).content
    assert out[:4] == b"RIFF" and out[8:12] == b"WEBP"
    assert b"<script" not in out


def test_inline_script_extraction_handles_every_end_tag_form():
    html = "<script>a()</script ><SCRIPT type=x>b()</SCRIPT\n><p>c()</p>"
    assert _inline_scripts(html) == ["a()", "b()"]
