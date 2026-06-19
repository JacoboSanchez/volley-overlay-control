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

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, Response
from fastapi.routing import APIRoute
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from app.overlay.auth import (
    _get_overlay_server_credential,  # noqa: F401  (re-export; see AUTHENTICATION.md §5)
    require_overlay_server_token,
)
from app.overlay.locale import _resolve_overlay_locale
from app.overlay.models import OverlayStateUpdate, RawConfigPayload
from app.overlay.state_store import OverlayStateStore
from app.overlay.themes import PRESET_THEMES, get_theme_names

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
    broadcast,  # ObsBroadcastHub — not type-hinted to avoid circular import
    templates: Jinja2Templates,
) -> APIRouter:
    """Create and return the overlay router with injected dependencies."""
    router = APIRouter(
        tags=["Overlay"],
        generate_unique_id_function=_deterministic_operation_id,
    )
    _register_page_routes(router, store, broadcast, templates)
    _register_api_routes(router, store, broadcast)
    return router


def _register_page_routes(
    router: APIRouter,
    store: OverlayStateStore,
    broadcast,
    templates: Jinja2Templates,
) -> None:
    """HTML pages + the OBS browser-source WebSocket."""

    # -- Favicon -----------------------------------------------------------

    @router.get("/favicon.ico", include_in_schema=False)
    async def favicon():
        return Response(content=b"", media_type="image/x-icon", status_code=200)

    # -- Overlay HTML rendering --------------------------------------------

    @router.get("/overlay/{public_token}", response_class=HTMLResponse)
    async def serve_overlay(
        request: Request, public_token: str, style: str = None,
        lang: str = None,
    ):
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
    async def serve_spectator(request: Request, public_token: str):
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
    async def obs_websocket(websocket: WebSocket, public_token: str):
        skey = await run_in_threadpool(_resolve_public_token, public_token)
        if skey is None:
            await websocket.close(code=4004, reason="Overlay not found")
            return
        overlay_id = skey
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


def _register_api_routes(
    router: APIRouter,
    store: OverlayStateStore,
    broadcast,
) -> None:
    """JSON API: state push, CRUD, raw config, output config, themes."""

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
