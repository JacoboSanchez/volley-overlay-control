"""Admin routes — custom overlay manager page and CRUD endpoints.

Two routers are exported:

* ``admin_page_router`` — serves the standalone HTML page at ``/manage``.
* ``admin_router`` — mounted under ``/api/v1/admin`` with JSON endpoints
  for listing, creating, copying and deleting custom overlays (the ones
  handled in-process by ``LocalOverlayBackend`` and persisted to
  ``data/overlay_state_{id}.json``).

Predefined overlay catalogues are configured outside the app, either via
the ``PREDEFINED_OVERLAYS`` environment variable or the remote
configurator, and are not editable from this surface.

All JSON endpoints require the ``OVERLAY_MANAGER_PASSWORD`` environment
variable to be set and the request to include a matching
``Authorization: Bearer <password>`` header.
"""

import copy
import logging
import os
import re
import time

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.auth_utils import get_admin_password, require_admin_token
from app.match_report_signing import (
    DEFAULT_TTL_SECONDS,
    MAX_TTL_SECONDS,
    MIN_TTL_SECONDS,
    make_signed_query,
)

logger = logging.getLogger(__name__)

_PAGE_PATH = os.path.join(os.path.dirname(__file__), "static", "overlays.html")

# Custom overlay IDs are used as filenames and URL path components, so
# only allow the characters that cannot collide with the filesystem or
# HTTP path parsing. The bare ID is used directly as the OID.
_OVERLAY_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CustomOverlayCreate(BaseModel):
    name: str = Field(..., min_length=1, description="Overlay id used as OID")
    copy_from: str | None = Field(
        None,
        description="Optional existing overlay id to clone configuration from",
    )


class CustomOverlayPatch(BaseModel):
    """Partial update for a custom overlay's appearance.

    Every field is optional — the patch is a thin admin-side wrapper around
    ``OverlayStateStore.update_state``. When ``theme`` is set, the matching
    preset from ``app.overlay.themes`` is applied first; ``colors`` and
    ``preferred_style`` are then merged on top so explicit overrides win
    over the theme defaults.
    """

    theme: str | None = Field(
        None,
        description=(
            "Apply a preset theme (e.g. 'dark', 'esports'). "
            "Available themes are listed by GET /api/themes."
        ),
    )
    colors: dict[str, str] | None = Field(
        None,
        description=(
            "Color overrides merged into overlay_control.colors. "
            "Common keys: set_bg, set_text, game_bg, game_text."
        ),
    )
    preferred_style: str | None = Field(
        None,
        description=(
            "Switch the Jinja template served at /overlay/{output_key}. "
            "Must match an entry in GET /api/config/{id}.availableStyles."
        ),
    )


class CustomOverlayUsage(BaseModel):
    """Snapshot of how many live consumers a custom overlay has."""

    obs_clients: int = Field(
        ..., description="Connected OBS / browser-source viewers."
    )
    frontend_ws_clients: int = Field(
        ...,
        description=(
            "Connected scoreboard control tabs (frontend WebSocket "
            "subscribers)."
        ),
    )
    has_active_session: bool = Field(
        ..., description="True when SessionManager has a live GameSession."
    )
    seconds_since_last_activity: int | None = Field(
        None,
        description=(
            "Seconds elapsed since the session was last touched; "
            "null when no session is active."
        ),
    )


class MatchSignUrlRequest(BaseModel):
    ttl_seconds: int | None = Field(
        default=None,
        ge=MIN_TTL_SECONDS,
        le=MAX_TTL_SECONDS,
        description=(
            "URL lifetime in seconds. Bounded to "
            f"[{MIN_TTL_SECONDS}, {MAX_TTL_SECONDS}]; defaults to "
            f"{DEFAULT_TTL_SECONDS}."
        ),
    )


class MatchSignUrlResponse(BaseModel):
    url: str = Field(
        ...,
        description=(
            "Absolute capability URL — anyone holding it can read "
            "the report until ``expires_at``."
        ),
    )
    expires_at: int = Field(
        ..., description="Unix-seconds expiry the URL was signed for.",
    )
    expires_in: int = Field(
        ..., description="Seconds remaining until expiry, at mint time.",
    )


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def require_admin(authorization: str = Header(None)) -> None:
    """Validate the admin Bearer token."""
    require_admin_token(
        authorization,
        token=None,
        # Bandit B106 false positive: this is the error message shown
        # when the password env var is unset, not a hardcoded credential.
        missing_password_detail=(  # nosec B106
            "Overlay management is disabled. "
            "Set OVERLAY_MANAGER_PASSWORD to enable it."
        ),
        missing_token_detail=(  # nosec B106
            "Missing admin password. Use 'Authorization: Bearer <password>'."
        ),
        invalid_token_detail="Invalid admin password.",  # nosec B106
    )


def _validate_overlay_id(value: str) -> str:
    name = (value or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Overlay name is required.")
    if not _OVERLAY_ID_PATTERN.fullmatch(name):
        raise HTTPException(
            status_code=400,
            detail="Overlay name may only contain letters, digits, '-', '_' and '.'.",
        )
    return name


def _overlay_store():
    from app.overlay import overlay_state_store
    return overlay_state_store


# ---------------------------------------------------------------------------
# Page router
# ---------------------------------------------------------------------------


admin_page_router = APIRouter(tags=["Admin"])


@admin_page_router.get("/manage", include_in_schema=False)
def manage_overlays_page():
    """Serve the standalone custom-overlay manager page."""
    if not os.path.isfile(_PAGE_PATH):
        raise HTTPException(status_code=500, detail="Admin page template not found.")
    return FileResponse(
        _PAGE_PATH,
        media_type="text/html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


# ---------------------------------------------------------------------------
# API router
# ---------------------------------------------------------------------------


admin_router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])


@admin_router.get("/status")
def admin_status():
    """Report whether overlay management is enabled on this server."""
    return {"enabled": get_admin_password() is not None}


@admin_router.post("/login")
def admin_login(_: None = Depends(require_admin)):
    """Validate the admin password. Returns ``{"ok": true}`` on success."""
    return {"ok": True}


@admin_router.get("/custom-overlays", dependencies=[Depends(require_admin)])
def list_custom_overlays():
    """Return every custom overlay persisted on disk.

    Each entry carries the overlay id (used directly as the OID) and its
    derived output key.
    """
    store = _overlay_store()
    return [
        {
            "id": entry["id"],
            "oid": entry["id"],
            "output_key": entry["output_key"],
        }
        for entry in store.list_overlays()
    ]


@admin_router.post("/custom-overlays", dependencies=[Depends(require_admin)])
def create_custom_overlay(payload: CustomOverlayCreate):
    """Create a new custom overlay, optionally cloning an existing one."""
    name = _validate_overlay_id(payload.name)
    store = _overlay_store()

    if store.overlay_exists(name):
        raise HTTPException(
            status_code=409, detail=f"Overlay '{name}' already exists.",
        )

    if payload.copy_from:
        source = _validate_overlay_id(payload.copy_from)
        if not store.overlay_exists(source):
            raise HTTPException(
                status_code=404,
                detail=f"Source overlay '{source}' not found.",
            )
        store.copy_overlay(source, name)
    else:
        store.create_overlay(name)

    return {
        "id": name,
        "oid": name,
        "output_key": store.get_output_key(name),
    }


@admin_router.post(
    "/match/{match_id}/sign-url",
    response_model=MatchSignUrlResponse,
    dependencies=[Depends(require_admin)],
    summary="Mint a short-lived signed URL for a match report",
)
def sign_match_report_url(
    match_id: str,
    payload: MatchSignUrlRequest,
    request: Request,
):
    """Return a capability URL the operator can paste into chat tools.

    The legacy share flow (``/match/{id}/report?token=<password>``)
    embeds the actual ``OVERLAY_MANAGER_PASSWORD`` in the URL —
    every browser bookmark, server log, or HTTP ``Referer`` that
    touches the link leaks the credential. This endpoint replaces
    that flow with an HMAC-signed URL of the form
    ``/match/{id}/report?exp=<ts>&sig=<hex>``: the password stays
    on the server and the URL expires automatically.

    Rotating the admin password invalidates every outstanding
    signed URL — that's the desired behaviour, since rotations are
    typically motivated by suspected leaks.

    The endpoint deliberately does *not* check whether the
    ``match_id`` exists: a 404 here would be a free oracle for
    enumerating archived matches by anyone holding the admin
    password (who could already do far worse anyway). Signing a
    bogus match id just produces a URL that 404s on use.
    """
    signed = make_signed_query(match_id, payload.ttl_seconds)
    if signed is None:
        # Should be unreachable — require_admin already 503's when
        # the password is unset — but guard anyway in case a future
        # refactor decouples the two.
        raise HTTPException(
            status_code=503,
            detail="Match-report signing requires OVERLAY_MANAGER_PASSWORD.",
        )
    base_url = str(request.base_url).rstrip("/")
    url = (
        f"{base_url}/match/{match_id}/report"
        f"?exp={signed['exp']}&sig={signed['sig']}"
    )
    return MatchSignUrlResponse(
        url=url,
        expires_at=signed["expires_at"],
        expires_in=max(0, signed["expires_at"] - int(time.time())),
    )


@admin_router.patch(
    "/custom-overlays/{name}",
    dependencies=[Depends(require_admin)],
    summary="Edit a custom overlay's theme / colors / preferred style",
)
async def patch_custom_overlay(name: str, payload: CustomOverlayPatch):
    """Apply a preset theme and/or merge colors / preferredStyle.

    Layering order matches the operator's mental model: the theme acts
    as a baseline, then explicit ``colors`` and ``preferred_style`` are
    merged on top. Empty patches are rejected with 400 so the operator
    sees a clear error rather than a silent no-op (which would mask
    accidental empty form submissions from the manager UI).
    """
    name = _validate_overlay_id(name)
    store = _overlay_store()

    if not store.overlay_exists(name):
        raise HTTPException(
            status_code=404, detail=f"Overlay '{name}' not found.",
        )

    if payload.theme is None and payload.colors is None and payload.preferred_style is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "Patch must specify at least one of: theme, colors, "
                "preferred_style."
            ),
        )

    # Validate first, then build a single merged payload so we hit
    # ``update_state`` exactly once — every call is one disk write plus
    # one WebSocket broadcast, so the previous "theme then overrides"
    # two-step doubled both costs for the common "apply a theme with
    # one tweak on top" flow.
    if payload.theme is not None:
        # Lazy import to avoid forcing the overlay package onto every test
        # path that imports the admin router.
        from app.overlay.themes import PRESET_THEMES, get_theme_names
        if payload.theme not in PRESET_THEMES:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Theme '{payload.theme}' not found. "
                    f"Available: {get_theme_names()}"
                ),
            )
        # Deep-copy the baseline so we can mutate it freely without
        # corrupting the shared catalogue entry.
        to_apply: dict = copy.deepcopy(PRESET_THEMES[payload.theme])
    else:
        to_apply = {}

    if payload.colors is not None or payload.preferred_style is not None:
        overlay_control = to_apply.setdefault("overlay_control", {})
        if payload.colors is not None:
            # Shallow-merge so explicit color keys override the theme's
            # values without erasing the ones the operator did not
            # supply. ``overlay_control["colors"] = payload.colors``
            # would lose ``set_text`` / ``game_text`` / etc. from the
            # theme baseline.
            base_colors = overlay_control.get("colors") or {}
            overlay_control["colors"] = {**base_colors, **payload.colors}
        if payload.preferred_style is not None:
            # Validate against the renderable templates so a typo can't
            # park the overlay on a 404 the next time it's served.
            renderable = store.get_renderable_styles()
            # ``default`` maps to ``index.html`` and is always present,
            # but it's not in get_available_styles_list because it's
            # also the implicit fallback. Accept it explicitly.
            if (
                payload.preferred_style != "default"
                and payload.preferred_style not in renderable
            ):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"preferred_style '{payload.preferred_style}' is not a "
                        f"known overlay style. Available: {renderable}"
                    ),
                )
            overlay_control["preferredStyle"] = payload.preferred_style

    if to_apply:
        await store.update_state(name, to_apply)

    logger.info(
        "Patched custom overlay '%s' (theme=%s, colors=%s, preferred_style=%s)",
        name,
        payload.theme,
        "yes" if payload.colors else "no",
        payload.preferred_style,
    )
    return {
        "id": name,
        "oid": name,
        "output_key": store.get_output_key(name),
    }


@admin_router.get(
    "/custom-overlays/{name}/usage",
    response_model=CustomOverlayUsage,
    dependencies=[Depends(require_admin)],
    summary="Inspect how many live consumers a custom overlay has",
)
def get_custom_overlay_usage(name: str):
    """Report live OBS / scoreboard / session counts for *name*.

    The response gives the operator enough information to decide whether
    deleting (or re-theming) the overlay will disrupt an in-progress
    broadcast — currently surfaced in the ``/manage`` UI as a dot next to
    each row.
    """
    name = _validate_overlay_id(name)
    store = _overlay_store()
    if not store.overlay_exists(name):
        raise HTTPException(
            status_code=404, detail=f"Overlay '{name}' not found.",
        )

    # Lazy imports — these modules carry heavy dependencies (asyncio task
    # registries, Backend) that we don't want loaded for every test that
    # imports admin.routes.
    from app.api.session_manager import SESSION_TTL_SECONDS, SessionManager
    from app.api.ws_hub import WSHub
    from app.overlay import obs_broadcast_hub

    obs_count = obs_broadcast_hub.get_client_count(name)
    frontend_count = len(WSHub._connections.get(name, set()))

    session = SessionManager._sessions.get(name)
    has_session = session is not None
    seconds_since: int | None = None
    if session is not None:
        # ``last_accessed`` uses ``time.monotonic`` (see GameSession.touch)
        # so we report a relative duration rather than a wall-clock
        # timestamp — matches the operator's question ("is this still
        # live?") and avoids the epoch-vs-monotonic confusion.
        elapsed = time.monotonic() - session.last_accessed
        # Clamp at the eviction TTL — anything older is considered stale
        # and should be GC'd by the next ``SessionManager.cleanup_expired``.
        seconds_since = max(0, min(int(elapsed), SESSION_TTL_SECONDS))

    return CustomOverlayUsage(
        obs_clients=obs_count,
        frontend_ws_clients=frontend_count,
        has_active_session=has_session,
        seconds_since_last_activity=seconds_since,
    )


@admin_router.post(
    "/webhooks/replay",
    dependencies=[Depends(require_admin)],
    summary="Re-deliver dead-lettered webhook records",
)
async def replay_dead_letter_webhooks(
    since: float | None = Query(
        None,
        description=(
            "Only replay records whose ``ts`` is >= this Unix-seconds "
            "value. Useful for restricting replay to entries that "
            "landed after the receiving service came back online."
        ),
    ),
    max_records: int = Query(
        50,
        ge=1,
        le=500,
        description=(
            "Cap the number of records redelivered in this call. "
            "``replay_records`` blocks on per-record retries with "
            "exponential backoff (~25 s worst case per record), so a "
            "fully-loaded dead-letter would otherwise pin the handler "
            "for tens of minutes. Use the ``remaining_in_dl`` field in "
            "the response to decide whether to call again."
        ),
    ),
):
    """Replay (a slice of) the webhook dead-letter file.

    Each record is matched to a configured ``WebhookTarget`` by URL,
    re-signed with the *current* HMAC secret (so rotating
    ``WEBHOOKS_SECRET`` doesn't strand legacy records with stale
    signatures), and re-attempted with the standard retry policy.

    * Successful redeliveries are removed from the file.
    * Records whose URL no longer matches any configured target are
      kept on disk so the operator can fix the config and retry.
    * Records that fail again are kept with their ``attempts``
      counter bumped and the latest ``last_error`` recorded.

    Selection order: oldest records (lowest ``ts``) within the
    eligible window go first, so iterative calls drain the file
    front-to-back. The blocking work runs on the FastAPI threadpool
    via ``run_in_threadpool`` so the event loop stays free for other
    handlers while a long replay is in flight.

    Returns counts only — the bodies are never echoed back so the
    admin surface cannot leak match payloads. ``remaining_in_dl``
    is the count of records still on disk after the call (ones held
    back by ``since`` / ``max_records`` plus the ``still_failing``
    bucket that just got re-written) so the operator knows whether
    to call again.
    """
    # Lazy imports keep ``app.admin.routes`` light for tests that just
    # exercise overlay CRUD; pulling in ``requests`` (via webhooks)
    # eagerly would tax those test paths.
    from app.api import webhook_dead_letter, webhooks
    records = webhook_dead_letter.read_all()
    if since is not None:
        eligible = [r for r in records if r.get("ts", 0) >= since]
        held_back = [r for r in records if r.get("ts", 0) < since]
    else:
        eligible = list(records)
        held_back = []
    # Replay the oldest-eligible slice so successive calls drain the
    # file front-to-back; what doesn't fit in this call stays in the
    # DL (``deferred``) and shows up in ``remaining_in_dl``.
    replay_set = eligible[:max_records]
    deferred = eligible[max_records:]
    dispatcher = webhooks.webhook_dispatcher
    succeeded, still_failing, skipped = await run_in_threadpool(
        dispatcher.replay_records, replay_set,
    )
    new_dl = held_back + deferred + still_failing
    webhook_dead_letter.replace_all(new_dl)
    return {
        "considered": len(replay_set),
        "succeeded": succeeded,
        "still_failing": len(still_failing),
        "skipped_unknown_url": skipped,
        "remaining_in_dl": len(new_dl),
    }


@admin_router.delete("/custom-overlays/{name}", dependencies=[Depends(require_admin)])
async def delete_custom_overlay(name: str):
    """Remove a custom overlay and its persisted state."""
    name = _validate_overlay_id(name)
    store = _overlay_store()
    existed = await run_in_threadpool(store.delete_overlay, name)
    if not existed:
        raise HTTPException(status_code=404, detail=f"Overlay '{name}' not found.")
    # Best-effort cleanup of the broadcast hub: the overlay is already gone,
    # so a stray exception here must not surface as a 500 to the operator.
    try:
        from app.overlay import obs_broadcast_hub
        await obs_broadcast_hub.cleanup_overlay(name)
    except Exception:  # nosec B110
        pass
    # Best-effort cleanup of the per-OID auxiliary state: same rationale.
    try:
        from app.api import action_log, match_archive
        from app.api.session_manager import SessionManager
        from app.api.session_persistence import delete_session_meta
        SessionManager.remove(name)
        delete_session_meta(name)
        action_log.delete(name)
        match_archive.delete_for_oid(name)
    except Exception:  # nosec B110
        pass
    return {"ok": True}
