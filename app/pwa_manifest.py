"""Runtime rewriting and personalization for SPA/PWA metadata."""

from __future__ import annotations

import html
import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_OPEN_TITLE_RE = re.compile(r"<title(?:\s[^>]*)?>", re.IGNORECASE)
_CLOSE_TITLE_RE = re.compile(r"</title\b[^>]*>", re.IGNORECASE)
_SKIP_BLOCK_RE = re.compile(
    r"<!--.*?-->|<script\b[^>]*>.*?</script\b[^>]*>|"
    r"<style\b[^>]*>.*?</style\b[^>]*>",
    re.IGNORECASE | re.DOTALL,
)


def _inject_title_into_html(html_content: str, title: str) -> str:
    """Replace the first top-level title, ignoring comments/scripts/styles."""
    skip_ranges = [
        (match.start(), match.end())
        for match in _SKIP_BLOCK_RE.finditer(html_content)
    ]

    def in_skip_range(offset: int) -> bool:
        return any(start <= offset < end for start, end in skip_ranges)

    for open_match in _OPEN_TITLE_RE.finditer(html_content):
        if in_skip_range(open_match.start()):
            continue
        close_match = _CLOSE_TITLE_RE.search(html_content, open_match.end())
        if close_match is None or in_skip_range(close_match.start()):
            continue
        replacement = f"<title>{html.escape(title)}</title>"
        return (
            html_content[: open_match.start()]
            + replacement
            + html_content[close_match.end() :]
        )
    return html_content


@lru_cache(maxsize=8)
def _render_index_html(path: str, mtime: float, title: str) -> str:
    """Return cached index HTML with the runtime application title."""
    text = Path(path).read_text(encoding="utf-8")
    return _inject_title_into_html(text, title)


@lru_cache(maxsize=8)
def _render_manifest(path: str, mtime: float, title: str) -> dict:
    """Return a cached manifest with runtime name fields."""
    with Path(path).open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    data["name"] = title
    data["short_name"] = title
    return data


_BOARD_TOKEN_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def _board_manifest(
    base: dict,
    title: str,
    username: str | None,
    oid: str,
) -> dict:
    """Return a per-board installable manifest without mutating *base*."""
    if username:
        start = (
            f"/board?u={quote(username, safe='')}&oid={quote(oid, safe='')}"
        )
    else:
        start = f"/board?oid={quote(oid, safe='')}"
    manifest = dict(base)
    manifest.update(
        start_url=start,
        id=start,
        scope="/",
        name=f"{title} · {oid}",
        short_name=oid,
        icons=[
            {
                "src": "icon-board.svg",
                "sizes": "any",
                "type": "image/svg+xml",
                "purpose": "any maskable",
            },
            {
                "src": "icon-board-192x192.png",
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any maskable",
            },
            {
                "src": "icon-board-512x512.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any maskable",
            },
        ],
    )
    return manifest


_MAX_MANIFEST_SHORTCUTS = 10


def _overlay_shortcuts(
    db: Session,
    cookie_token: str | None,
) -> list[dict]:
    """Return shortcuts for the signed-in owner's overlays."""
    if not cookie_token:
        return []
    try:
        from app.auth import sessions
        from app.overlays_service import list_overlays

        user = sessions.resolve_session(db, cookie_token)
        if user is None:
            return []
        overlays = list_overlays(db, user.id)
    except Exception:
        logger.exception("Failed to build PWA manifest shortcuts")
        return []

    shortcuts: list[dict] = []
    for overlay in overlays[:_MAX_MANIFEST_SHORTCUTS]:
        oid = overlay.oid
        shortcut: dict = {
            "name": oid,
            "short_name": oid,
            "url": f"/board?oid={quote(oid, safe='')}",
            "icons": [
                {
                    "src": "icon-board-192x192.png",
                    "sizes": "192x192",
                    "type": "image/png",
                }
            ],
        }
        if overlay.description:
            shortcut["description"] = overlay.description
        shortcuts.append(shortcut)
    return shortcuts


def _with_overlay_shortcuts(
    content: dict,
    db: Session,
    cookie_token: str | None,
) -> dict:
    """Return a manifest copy with shortcuts when a user is signed in."""
    shortcuts = _overlay_shortcuts(db, cookie_token)
    if not shortcuts:
        return content
    manifest = dict(content)
    manifest["shortcuts"] = shortcuts
    return manifest
