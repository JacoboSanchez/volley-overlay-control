"""HTTP + WebSocket routes for serving overlays to OBS browser sources.

Ported from volleyball-scoreboard-overlay/main.py.  All routes are created
inside a factory function so the ``OverlayStateStore`` and
``ObsBroadcastHub`` singletons can be injected.
"""

import json
import logging
import os
import re
import time
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, Response
from fastapi.routing import APIRoute
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict
from starlette.concurrency import run_in_threadpool

from app.auth_utils import get_hashed_or_plaintext_env, require_admin
from app.match_report_i18n import (
    SUPPORTED_LOCALES,
)
from app.match_report_i18n import (
    resolve_locale as _resolve_accept_language,
)
from app.overlay.state_store import OverlayStateStore
from app.overlay.themes import PRESET_THEMES, get_theme_names
from app.password_hash import verify_password

logger = logging.getLogger(__name__)


def _normalise_locale(raw: str | None) -> str | None:
    if not raw or not isinstance(raw, str):
        return None
    candidate = raw.strip().lower()[:2]
    return candidate if candidate in SUPPORTED_LOCALES else None


def _resolve_overlay_locale(
    query_lang: str | None,
    request: Request,
    persisted_locale: str | None = None,
) -> str:
    """Pick the locale tag the overlay templates / JS will use.

    Resolution order: ``?lang=<code>`` query param (operator override
    when embedding the overlay in OBS) → ``raw_remote_customization.locale``
    persisted with the overlay (operator's UI language, pushed live by
    the control app so OBS browser sources whose URL is fixed in the
    streaming app still follow language changes) → ``OVERLAY_LOCALE``
    env var → ``Accept-Language`` (q-weighted via
    :func:`app.match_report_i18n.resolve_locale`) → ``"en"``.
    """
    for candidate in (query_lang, persisted_locale, os.environ.get("OVERLAY_LOCALE")):
        normalised = _normalise_locale(candidate)
        if normalised is not None:
            return normalised
    return _resolve_accept_language(request.headers.get("accept-language"))


def _get_overlay_server_credential() -> str | None:
    """Return the configured overlay-server credential, hash-preferred.

    ``OVERLAY_SERVER_TOKEN_HASH`` (a scrypt record from
    :mod:`app.password_hash`) wins over the legacy plaintext
    ``OVERLAY_SERVER_TOKEN`` when both are set, so an operator
    migrating to hashed credentials does not have to delete the
    plaintext to switch over. Returns ``None`` when neither is set.
    """
    return get_hashed_or_plaintext_env(
        "OVERLAY_SERVER_TOKEN_HASH",
        "OVERLAY_SERVER_TOKEN",
    )


def require_overlay_server_token(authorization: str = Header(None)) -> None:
    """Gate overlay-server mutation / leaky read endpoints.

    ``OVERLAY_SERVER_TOKEN`` is normally populated at startup by
    :func:`app.security_bootstrap.ensure_overlay_server_token` (auto-
    generated on first run, persisted to ``data/.overlay_server_token``).
    Operators who prefer hash-only configuration can set
    ``OVERLAY_SERVER_TOKEN_HASH`` instead — the bootstrap detects
    that and skips auto-generation.

    When either credential is set the request must include
    ``Authorization: Bearer <token>``; verification goes through
    :func:`app.password_hash.verify_password` which accepts plaintext
    or hash records (constant-time in either branch). The dependency
    stays a no-op only when the operator explicitly opted into legacy
    fail-open via ``OVERLAY_SERVER_TOKEN_DISABLED=true`` — see
    ``AUTHENTICATION.md`` §5 for the migration notes.
    """
    expected = _get_overlay_server_credential()
    if expected is None:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing overlay server token. Use 'Authorization: Bearer <token>'.",
            # RFC 7235 §4.1: 401 responses must advertise the auth
            # scheme. ``realm="overlay-server"`` distinguishes this
            # ladder from the scoreboard and admin ones in client
            # / proxy logs.
            headers={"WWW-Authenticate": 'Bearer realm="overlay-server"'},
        )
    provided = authorization.removeprefix("Bearer ").strip()
    if not verify_password(provided, expected):
        raise HTTPException(status_code=403, detail="Invalid overlay server token.")


# ---------------------------------------------------------------------------
# Pydantic models (same contract as the original overlay server)
# ---------------------------------------------------------------------------


class TeamStateModel(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str | None = None
    short_name: str | None = None
    color_primary: str | None = None
    color_secondary: str | None = None
    logo_url: str | None = None
    sets_won: int | None = None
    points: int | None = None
    serving: bool | None = None
    timeouts_taken: int | None = None
    set_history: dict[str, int] | None = None


class MatchInfoModel(BaseModel):
    model_config = ConfigDict(extra="allow")
    tournament: str | None = None
    phase: str | None = None
    best_of_sets: int | None = None
    current_set: int | None = None
    show_only_current_set: bool | None = None


class OverlayControlModel(BaseModel):
    model_config = ConfigDict(extra="allow")
    show_main_scoreboard: bool | None = None
    show_bottom_ticker: bool | None = None
    ticker_message: str | None = None
    show_player_stats: bool | None = None
    player_stats_data: Any | None = None
    geometry: dict[str, Any] | None = None
    colors: dict[str, str] | None = None
    preferredStyle: str | None = None


class OverlayStateUpdate(BaseModel):
    model_config = ConfigDict(extra="allow")
    match_info: MatchInfoModel | None = None
    team_home: TeamStateModel | None = None
    team_away: TeamStateModel | None = None
    overlay_control: OverlayControlModel | None = None
    raw_remote_model: Any | None = None
    raw_remote_customization: Any | None = None


class RawConfigPayload(BaseModel):
    model_config = ConfigDict(extra="allow")
    model: Any | None = None
    customization: Any | None = None


# ---------------------------------------------------------------------------
# Router factory
# ---------------------------------------------------------------------------


def create_overlay_router(
    store: OverlayStateStore,
    broadcast,  # ObsBroadcastHub — not type-hinted to avoid circular import
    templates: Jinja2Templates,
) -> APIRouter:
    """Create and return the overlay router with injected dependencies."""

    def _deterministic_operation_id(route: APIRoute) -> str:
        """Sort ``route.methods`` so multi-method routes get a stable id.

        FastAPI's default generator does ``list(route.methods)[0]`` on a set,
        which yields different results across Python processes and makes the
        OpenAPI snapshot flap between runs.
        """
        methods = sorted(route.methods or [])
        method_suffix = "_".join(m.lower() for m in methods)
        name = re.sub(r"\W", "_", f"{route.name}{route.path_format}")
        return f"{name}_{method_suffix}" if method_suffix else name

    router = APIRouter(
        tags=["Overlay"],
        generate_unique_id_function=_deterministic_operation_id,
    )

    # -- Favicon -----------------------------------------------------------

    @router.get("/favicon.ico", include_in_schema=False)
    async def favicon():
        return Response(content=b"", media_type="image/x-icon", status_code=200)

    # -- Overlay HTML rendering --------------------------------------------

    @router.get("/overlay/{overlay_id}", response_class=HTMLResponse)
    async def serve_overlay(
        request: Request, overlay_id: str, style: str = None,
        lang: str = None,
    ):
        resolved = await run_in_threadpool(store.resolve_overlay_id, overlay_id)
        if resolved is None:
            raise HTTPException(status_code=404, detail="Overlay ID not found.")
        overlay_id = resolved

        available = await run_in_threadpool(store.get_available_styles_list)
        renderable = await run_in_threadpool(store.get_renderable_styles)

        # Read the in-memory snapshot (lazy-loaded from disk on first
        # touch). ``preferredStyle`` and the operator-chosen ``locale``
        # both live on ``raw_remote_customization`` so the page boots in
        # the right language and style before any WS update arrives.
        state = await run_in_threadpool(store.get_state, overlay_id)
        customization = state.get("raw_remote_customization") or {}

        if not style:
            preferred = customization.get("preferredStyle")
            if preferred and preferred in available:
                style = preferred
            else:
                style = "default"

        # Validate style against known templates to prevent path traversal.
        # `renderable` is a superset of `available` that includes meta-styles
        # like `mosaic` (hidden from the picker but valid as a URL param).
        if style not in renderable:
            raise HTTPException(
                status_code=404,
                detail=f"Overlay style '{style}' not found.",
            )

        template_name = "index.html" if style == "default" else f"{style}.html"

        persisted_locale = customization.get("locale")

        return templates.TemplateResponse(
            request=request,
            name=template_name,
            context={
                "target_id": overlay_id,
                "output_key": OverlayStateStore.get_output_key(overlay_id),
                "style": style,
                "available_styles": available,
                "v": int(time.time()),
                "locale": _resolve_overlay_locale(
                    lang, request, persisted_locale,
                ),
            },
        )

    # -- Public spectator (follow) page ------------------------------------

    @router.get("/follow/{overlay_id}", response_class=HTMLResponse)
    async def serve_spectator(request: Request, overlay_id: str):
        """Mobile-friendly read-only follow view.

        Resolves the overlay id like ``/overlay/{id}`` and serves a
        lightweight template that consumes the same ``/ws/{id}`` feed
        the OBS templates use. Public by design — the page exposes no
        write paths and inherits the same data exposure as the OBS
        overlay it shadows.
        """
        resolved = await run_in_threadpool(store.resolve_overlay_id, overlay_id)
        if resolved is None:
            raise HTTPException(status_code=404, detail="Overlay ID not found.")
        overlay_id = resolved

        return templates.TemplateResponse(
            request=request,
            name="_spectator.html",
            context={
                "target_id": overlay_id,
                "output_key": OverlayStateStore.get_output_key(overlay_id),
                "v": int(time.time()),
            },
        )

    # -- OBS browser source WebSocket --------------------------------------

    @router.websocket("/ws/{overlay_id}")
    async def obs_websocket(websocket: WebSocket, overlay_id: str):
        resolved = await run_in_threadpool(store.resolve_overlay_id, overlay_id)
        if resolved is None:
            await websocket.close(code=4004, reason="Overlay not found")
            return
        overlay_id = resolved
        await websocket.accept()

        broadcast.add_client(overlay_id, websocket)

        try:
            state = await run_in_threadpool(store.get_state, overlay_id)
            await websocket.send_text(json.dumps(state))
            while True:
                data = await websocket.receive_text()
                if data == "ping":
                    await websocket.send_text("pong")
        except WebSocketDisconnect:
            pass
        finally:
            broadcast.remove_client(overlay_id, websocket)

    # -- State update (HTTP) -----------------------------------------------

    @router.post(
        "/api/state/{overlay_id}",
        dependencies=[Depends(require_overlay_server_token)],
    )
    async def update_state(
        overlay_id: str, state_update: OverlayStateUpdate
    ):
        update_dict = state_update.model_dump(exclude_unset=True)
        await store.update_state(overlay_id, update_dict)
        return {"status": "success", "overlay_id": overlay_id}

    # -- Overlay CRUD ------------------------------------------------------

    @router.api_route(
        "/create/overlay/{overlay_id}",
        methods=["GET", "POST"],
        dependencies=[Depends(require_overlay_server_token)],
    )
    async def create_overlay(overlay_id: str):
        if store.overlay_exists(overlay_id):
            return {"status": "already_exists", "overlay_id": overlay_id}
        store.create_overlay(overlay_id)
        return {"status": "created", "overlay_id": overlay_id}

    @router.api_route(
        "/delete/overlay/{overlay_id}",
        methods=["GET", "POST", "DELETE"],
        dependencies=[Depends(require_overlay_server_token)],
    )
    async def delete_overlay(overlay_id: str):
        existed = store.delete_overlay(overlay_id)
        await broadcast.cleanup_overlay(overlay_id)
        if existed:
            return {"status": "deleted", "overlay_id": overlay_id}
        raise HTTPException(status_code=404, detail="Overlay not found")

    @router.get("/list/overlay", dependencies=[Depends(require_admin)])
    async def list_overlays():
        """Return every overlay id plus its output key.

        Gated behind ``OVERLAY_MANAGER_PASSWORD`` because the response
        defeats the capability-URL design of ``/overlay/{output_key}``.
        See ``AUTHENTICATION.md`` (F-4).
        """
        return {"overlays": store.list_overlays()}

    # -- Raw config --------------------------------------------------------

    @router.get(
        "/api/raw_config/{overlay_id}",
        dependencies=[Depends(require_overlay_server_token)],
    )
    async def get_raw_config(overlay_id: str):
        if not store.overlay_exists(overlay_id):
            raise HTTPException(
                status_code=404, detail="Overlay not found"
            )
        return store.get_raw_config(overlay_id)

    @router.post(
        "/api/raw_config/{overlay_id}",
        dependencies=[Depends(require_overlay_server_token)],
    )
    async def set_raw_config(overlay_id: str, payload: RawConfigPayload):
        if not store.overlay_exists(overlay_id):
            raise HTTPException(
                status_code=404,
                detail="Overlay not found. Call /create/overlay/ first.",
            )
        store.set_raw_config(
            overlay_id,
            model=payload.model,
            customization=payload.customization,
        )
        return {"status": "success"}

    # -- Config / output URL -----------------------------------------------

    @router.get(
        "/api/config/{overlay_id}",
        dependencies=[Depends(require_overlay_server_token)],
    )
    async def get_config(request: Request, overlay_id: str):
        public_url = os.environ.get("OVERLAY_PUBLIC_URL", "").rstrip("/")
        base_url = (
            f"{public_url}/" if public_url else str(request.base_url)
        )
        output_key = OverlayStateStore.get_output_key(overlay_id)
        output_url = f"{base_url}overlay/{output_key}"

        return {
            "outputUrl": output_url,
            "outputKey": output_key,
            "availableStyles": store.get_available_styles_list(),
        }

    # -- Themes ------------------------------------------------------------

    @router.get("/api/themes")
    async def list_themes():
        return {"themes": get_theme_names()}

    @router.post(
        "/api/theme/{overlay_id}/{theme_name}",
        dependencies=[Depends(require_overlay_server_token)],
    )
    async def apply_theme(overlay_id: str, theme_name: str):
        if theme_name not in PRESET_THEMES:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Theme '{theme_name}' not found. "
                    f"Available: {get_theme_names()}"
                ),
            )
        if not store.overlay_exists(overlay_id):
            raise HTTPException(
                status_code=404, detail="Overlay not found"
            )
        await store.update_state(overlay_id, PRESET_THEMES[theme_name])
        logger.info(
            "Theme '%s' applied to overlay '%s'", theme_name, overlay_id
        )
        return {
            "status": "applied",
            "theme": theme_name,
            "overlay_id": overlay_id,
        }

    return router
