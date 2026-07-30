"""Link policy and URL assembly for a board session."""

import logging
import urllib.parse

from fastapi import Request
from starlette.concurrency import run_in_threadpool

from app.api import match_archive
from app.api.session_manager import GameSession
from app.env_vars_manager import EnvVarsManager

logger = logging.getLogger(__name__)


async def build_overlay_links(
    request: Request,
    session: GameSession,
) -> dict[str, str]:
    """Return overlay, preview, and spectator links for the session."""
    # ``raw_oid`` for backend resolution; ``skey`` (== session.oid) for
    # per-user archive lookups.
    oid = session.raw_oid
    skey = session.oid
    output = session.conf.output
    links: dict[str, str] = {}

    if output and output.strip():
        links["overlay"] = output

        # Build a preview-page URL pointing at the SPA /preview route. The
        # in-app preview card consumes the geometry params from this URL, and
        # users can also open it directly as a standalone scalable preview.
        # The in-process overlay reports its own render bounds via postMessage
        # (layout_id=auto); geometry params are ignored there but kept for a
        # uniform URL shape.
        styles: list[str] = []
        try:
            styles = await run_in_threadpool(session.backend.get_available_styles, oid) or []
        except Exception:
            logger.exception("Failed to fetch available styles for preview")
            styles = []

        base_url = str(request.base_url).rstrip("/")
        qs_params = {
            "output": output,
            "x": 0.0,
            "y": 0.0,
            "width": 100.0,
            "height": 100.0,
            "layout_id": "auto",
        }
        if len(styles) > 1:
            qs_params["styles"] = ",".join(styles)
        preview_qs = urllib.parse.urlencode(qs_params)
        links["preview"] = f"{base_url}/preview?{preview_qs}"

        # Public spectator (follow) page — the mobile-first read-only view that
        # consumes the OBS WS broadcast over the same public token.
        if session.public_token:
            links["follow"] = f"{base_url}/follow/{session.public_token}"

    # Surface the latest archived match report — but only when the
    # report endpoint is publicly readable. When reports are gated to
    # the owner (cookie) / signed URLs, we deliberately do NOT embed a
    # link here: the spectator-facing ``/links`` payload has no
    # credential to offer, and the owner reaches reports from their
    # account screen instead.
    raw_public = EnvVarsManager.get_env_var("MATCH_REPORT_PUBLIC", "false")
    if str(raw_public).strip().lower() in ("1", "true", "t", "yes", "on"):
        latest = await run_in_threadpool(_latest_match_id_for, skey)
        if latest is not None:
            base_url = str(request.base_url).rstrip("/")
            links["latest_match_report"] = f"{base_url}/match/{latest}/report"
            # Public per-overlay history page, keyed by the unguessable
            # public_token (same capability as the overlay/follow links).
            if session.public_token:
                links["match_history"] = f"{base_url}/matches/{session.public_token}"

    return links


def _latest_match_id_for(oid: str) -> str | None:
    """Return the most-recent ``match_id`` archived for *oid*, or ``None``."""
    summaries = match_archive.list_matches(oid=oid, limit=1)
    return summaries[0]["match_id"] if summaries else None
