"""Overlay template discovery and per-style capability introspection."""

from __future__ import annotations

import os
import re
import threading

# Bundled overlay static CSS directory, resolved relative to this module
# (app/overlay/) so capability scanning finds the shipped stylesheets
# regardless of the templates directory supplied by callers.
_BUNDLED_CSS_DIR = os.path.normpath(
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..",
        "..",
        "overlay_static",
        "css",
    )
)


class StyleCatalog:
    """Discover selectable/renderable templates and their UI capabilities."""

    # Meta-styles are renderable via /overlay/{id}?style=... but hidden from
    # the style picker. ``base`` is an abstract parent and is never served.
    _META_STYLES = {"mosaic"}
    _NEVER_RENDERED = {"base"}

    # Pull linked stylesheet names from templates and one-level CSS imports.
    _CSS_HREF_RE = re.compile(r"/static/css/([\w-]+)\.css")
    _CSS_IMPORT_RE = re.compile(r"@import\s+url\(['\"]?([\w-]+)\.css")

    def __init__(
        self,
        templates_dir: str,
        *,
        lock: threading.RLock | None = None,
    ) -> None:
        self._templates_dir = templates_dir
        self._lock = lock or threading.RLock()
        self._available_styles: list | None = None
        self._renderable_styles: list | None = None
        self._style_capabilities: dict[str, dict[str, bool]] | None = None

    def get_available_styles_list(self) -> list:
        """Return user-selectable overlay styles (cached after first scan)."""
        with self._lock:
            if self._available_styles is not None:
                return self._available_styles
            hidden = self._META_STYLES | self._NEVER_RENDERED
            styles = []
            if os.path.isdir(self._templates_dir):
                for filename in os.listdir(self._templates_dir):
                    if not filename.endswith(".html"):
                        continue
                    name = filename[:-5]
                    # Underscore-prefixed templates are private layouts/pages.
                    if name.startswith("_"):
                        continue
                    label = "default" if name == "index" else name
                    if label not in hidden:
                        styles.append(label)
            self._available_styles = sorted(styles)
            return self._available_styles

    def get_renderable_styles(self) -> list:
        """Return styles accepted by the overlay route, including meta-styles."""
        with self._lock:
            if self._renderable_styles is not None:
                return self._renderable_styles
            styles = list(self.get_available_styles_list())
            for meta in self._META_STYLES:
                if os.path.isfile(
                    os.path.join(self._templates_dir, f"{meta}.html")
                ):
                    styles.append(meta)
            self._renderable_styles = styles
            return self._renderable_styles

    @staticmethod
    def _read_text(path: str) -> str:
        """Return the file contents at *path*, or ``""`` if unreadable."""
        try:
            with open(path, encoding="utf-8") as handle:
                return handle.read()
        except OSError:
            return ""

    def _template_supports_theme(self, html: str, css_dir: str) -> bool:
        """Return whether linked stylesheets define a light/dark override."""
        seen: set[str] = set()
        queue = list(self._CSS_HREF_RE.findall(html))
        while queue:
            name = queue.pop()
            if name in seen:
                continue
            seen.add(name)
            css = self._read_text(os.path.join(css_dir, f"{name}.css"))
            if "overlay-theme" in css:
                return True
            queue.extend(self._CSS_IMPORT_RE.findall(css))
        return False

    def get_style_capabilities(self) -> dict[str, dict[str, bool]]:
        """Return cached capability flags derived from templates and CSS."""
        with self._lock:
            if self._style_capabilities is not None:
                return self._style_capabilities
            caps: dict[str, dict[str, bool]] = {}
            for style in self.get_available_styles_list():
                template = (
                    "index.html" if style == "default" else f"{style}.html"
                )
                html = self._read_text(
                    os.path.join(self._templates_dir, template)
                )
                caps[style] = {
                    "verticalAnchor": "data-fixed-geometry" in html,
                    "theme": self._template_supports_theme(
                        html, _BUNDLED_CSS_DIR
                    ),
                }
            self._style_capabilities = caps
            return caps
