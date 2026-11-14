"""HTTP + WebSocket routes for serving overlays to OBS browser sources.

Ported from volleyball-scoreboard-overlay/main.py.  All routes are created
inside a factory function so the ``OverlayStateStore`` and
``ObsBroadcastHub`` singletons can be injected.
"""

import json
import logging
import re
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.routing import APIRoute
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from app.overlay.broadcast import ObsBroadcastHub, ObsHubFull
from app.overlay.locale import _resolve_overlay_locale
from app.overlay.payload_schema import public_overlay_state
from app.overlay.state_store import OverlayStateStore
from app.overlay.style_preview import register_style_preview
from app.overlay.themes import get_theme_names

logger = logging.getLogger(__name__)


# Overlay pages embed a per-render ``?v=`` cache-buster on their JS/CSS so a
# new deploy is picked up on the next load. That only holds if the HTML page
# itself is never cached — otherwise a proxy/CDN can freeze the ``?v`` and keep
# serving the stale assets it points at (the page looks "stuck" on old code
# even though the bare ``/static`` URLs are fresh). Mark these dynamic pages
# no-store so intermediaries always re-fetch them.
_NO_CACHE_HEADERS = {"Cache-Control": "no-cache, no-store, must-revalidate"}


def _resolve_public_token(token: str) -> str | None:
    """Map a public OBS-output token to its overlay storage key (skey).

    The public surface (``/overlay``, ``/follow``, ``/ws``) is addressed by
    the unguessable ``public_token`` stored on the user's overlay row, never
    by the user-facing ``username``/``oid`` — so the OBS URL leaks neither.
    """
    from app import overlays_service
    from app.db.engine import session_scope

    if not token:
        return None
    with session_scope() as db:
        overlay = overlays_service.get_by_public_token(db, token)
        if overlay is None:
            return None
        return overlays_service.skey_for(overlay)



def _public_base_url(request: Request) -> str:
    from app.api.overlay_links_service import public_base_url

    return public_base_url(request)


def _team_catalog(token: str, group: str | None, base_url: str) -> dict[str, Any]:
    """The catalog of the teams (or one group) of the overlay *token* belongs to.

    Raises 404 for an unknown token and for a group its owner cannot see, so
    the answer never tells another user's group from a missing one.
    """
    from app import overlays_service, team_catalog_transfer, teams_service
    from app.db.engine import session_scope
    from app.overlay_key import split_skey

    with session_scope() as db:
        overlay = overlays_service.get_by_public_token(db, token) if token else None
        if overlay is None:
            raise HTTPException(status_code=404, detail="Overlay ID not found.")
        owner_id, _oid = split_skey(overlays_service.skey_for(overlay))
        group_id: int | None = None
        if group is not None and group.strip().casefold() not in ("", "all"):
            found = teams_service.find_visible_group(db, owner_id, group)
            if found is None:
                raise HTTPException(status_code=404, detail="Group not found.")
            group_id = found.id
        teams = teams_service.group_effective_teams(db, owner_id, group_id)
        catalog = team_catalog_transfer.catalog_of_teams(teams, base_url=base_url)
        return catalog.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Router factory
# ---------------------------------------------------------------------------


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


def create_overlay_router(
    store: OverlayStateStore,
    broadcast: ObsBroadcastHub,
    templates: Jinja2Templates,
) -> APIRouter:
    """Create and return the overlay router with injected dependencies."""
    router = APIRouter(
        tags=["Overlay"],
        generate_unique_id_function=_deterministic_operation_id,
    )
    _register_page_routes(router, store, broadcast, templates)
    register_style_preview(router, store, templates)
    _register_api_routes(router, store, broadcast)
    return router


def _register_page_routes(
    router: APIRouter,
    store: OverlayStateStore,
    broadcast: ObsBroadcastHub,
    templates: Jinja2Templates,
) -> None:
    """HTML pages + the OBS browser-source WebSocket."""

    # -- Favicon -----------------------------------------------------------

    @router.get("/favicon.ico", include_in_schema=False)
    async def favicon() -> Response:
        return Response(content=b"", media_type="image/x-icon", status_code=200)

    # -- Overlay HTML rendering --------------------------------------------

    @router.get("/overlay/{public_token}", response_class=HTMLResponse)
    async def serve_overlay(
        request: Request,
        public_token: str,
        style: str | None = None,
        lang: str | None = None,
    ) -> Response:
        skey = await run_in_threadpool(_resolve_public_token, public_token)
        if skey is None:
            raise HTTPException(status_code=404, detail="Overlay ID not found.")
        overlay_id = skey

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
        capabilities = await run_in_threadpool(store.get_style_capabilities)
        style_capability = capabilities.get(style, {})
        native_theme = style_capability.get("nativeTheme", "dark")
        if native_theme not in ("dark", "light"):
            native_theme = "dark"

        persisted_locale = customization.get("locale")

        return templates.TemplateResponse(
            request=request,
            name=template_name,
            context={
                # The page connects to /ws/{output_key}; both the OBS URL
                # token and the WS subscription use the public token, which
                # the WS route resolves back to the storage key.
                "target_id": public_token,
                "output_key": public_token,
                "style": style,
                "native_theme": native_theme,
                "available_styles": available,
                "v": int(time.time()),
                "locale": _resolve_overlay_locale(
                    lang, request, persisted_locale,
                ),
            },
            headers=_NO_CACHE_HEADERS,
        )

    # -- Public spectator (follow) page ------------------------------------

    @router.get("/follow/{public_token}", response_class=HTMLResponse)
    async def serve_spectator(
        request: Request,
        public_token: str,
    ) -> Response:
        """Mobile-friendly read-only follow view.

        Resolves the public token like ``/overlay/{token}`` and serves a
        lightweight template that consumes the same ``/ws/{token}`` feed
        the OBS templates use. Public by design — the page exposes no
        write paths and inherits the same data exposure as the OBS
        overlay it shadows.
        """
        skey = await run_in_threadpool(_resolve_public_token, public_token)
        if skey is None:
            raise HTTPException(status_code=404, detail="Overlay ID not found.")

        return templates.TemplateResponse(
            request=request,
            name="_spectator.html",
            context={
                "target_id": public_token,
                "output_key": public_token,
                "v": int(time.time()),
            },
            headers=_NO_CACHE_HEADERS,
        )

    # -- OBS browser source WebSocket --------------------------------------

    @router.websocket("/ws/{public_token}")
    async def obs_websocket(websocket: WebSocket, public_token: str) -> None:
        skey = await run_in_threadpool(_resolve_public_token, public_token)
        if skey is None:
            await websocket.close(code=4004, reason="Overlay not found")
            return
        overlay_id = skey
        try:
            # Register before accepting so a capped overlay is refused with
            # a clean 1013 close (same shape as the control WS endpoint).
            broadcast.add_client(overlay_id, websocket)
        except ObsHubFull as exc:
            logger.warning(
                "Refused OBS WS connect for overlay '%s' — at cap %d",
                overlay_id, exc.cap,
            )
            await websocket.close(code=1013, reason="Too many clients for this overlay.")
            return
        try:
            await websocket.accept()
            state = await run_in_threadpool(store.get_state, overlay_id)
            await websocket.send_text(json.dumps(public_overlay_state(state)))
            while True:
                data = await websocket.receive_text()
                if data == "ping":
                    await websocket.send_text("pong")
        except WebSocketDisconnect:
            pass
        finally:
            broadcast.remove_client(overlay_id, websocket)


def _register_api_routes(
    router: APIRouter,
    store: OverlayStateStore,
    broadcast: ObsBroadcastHub,
) -> None:
    """Public JSON API for the in-process overlay engine.

    Overlay state is driven in-process by ``LocalOverlayBackend`` (direct
    ``OverlayStateStore`` calls), so there are no externally-callable
    mutation/config endpoints — only the read-only theme list used by the
    overlay templates, a read-only snapshot of one overlay's state and its
    owner's team catalog.
    """

    @router.get(
        "/api/state/{public_token}",
        summary="Current overlay state (same document /ws/{public_token} sends)",
    )
    async def overlay_state_snapshot(public_token: str) -> JSONResponse:
        """One-shot HTTP read of the state an OBS source gets on connect.

        For integrations that need the match as it stands (teams, colours,
        logos, score) without holding a WebSocket open. Same capability and
        same projection as ``/ws/{public_token}``: output only.
        """
        skey = await run_in_threadpool(_resolve_public_token, public_token)
        if skey is None:
            raise HTTPException(status_code=404, detail="Overlay ID not found.")
        state: dict[str, Any] = await run_in_threadpool(store.get_state, skey)
        return JSONResponse(public_overlay_state(state), headers=_NO_CACHE_HEADERS)

    @router.get(
        "/api/teams/{public_token}",
        summary="The overlay owner's teams as a team catalog document",
    )
    async def overlay_team_catalog(
        request: Request,
        public_token: str,
        group: str | None = Query(
            None,
            max_length=120,
            description="Name or id of one of the owner's groups; omit (or `all`) for every team.",
        ),
    ) -> JSONResponse:
        """The teams the overlay's owner can pick from, for tools that sync teams.

        Read-only, and addressed by the output token like the state above, so
        a tool that only needs the team list is never handed the control
        token. Hosted logos are absolute URLs rather than embedded data.
        """
        catalog = await run_in_threadpool(
            _team_catalog, public_token, group, _public_base_url(request),
        )
        return JSONResponse(catalog, headers=_NO_CACHE_HEADERS)

    @router.get("/api/themes")
    async def list_themes() -> dict[str, list[str]]:
        return {"themes": get_theme_names()}
