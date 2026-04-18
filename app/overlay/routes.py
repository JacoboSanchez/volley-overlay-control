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
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, Response
from fastapi.routing import APIRoute
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict

from app.admin.routes import require_admin
from app.env_vars_manager import EnvVarsManager
from app.overlay.state_store import OverlayStateStore, deep_merge, normalize_state

logger = logging.getLogger(__name__)


def _get_overlay_server_token() -> Optional[str]:
    """Return the configured overlay-server token (or None if unset)."""
    token = EnvVarsManager.get_env_var("OVERLAY_SERVER_TOKEN", None)
    if token is None:
        return None
    token = token.strip()
    return token or None


def require_overlay_server_token(authorization: str = Header(None)) -> None:
    """Gate overlay-server mutation / leaky read endpoints.

    When ``OVERLAY_SERVER_TOKEN`` is unset the check is a no-op so
    existing deployments keep working (with a startup warning; see
    ``AUTHENTICATION.md`` F-3 and F-5). When the env var is set, the
    request must include ``Authorization: Bearer <token>``.
    """
    token = _get_overlay_server_token()
    if token is None:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing overlay server token. Use 'Authorization: Bearer <token>'.",
        )
    provided = authorization.removeprefix("Bearer ").strip()
    if provided != token:
        raise HTTPException(status_code=403, detail="Invalid overlay server token.")


# ---------------------------------------------------------------------------
# Pydantic models (same contract as the original overlay server)
# ---------------------------------------------------------------------------


class TeamStateModel(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: Optional[str] = None
    short_name: Optional[str] = None
    color_primary: Optional[str] = None
    color_secondary: Optional[str] = None
    logo_url: Optional[str] = None
    sets_won: Optional[int] = None
    points: Optional[int] = None
    serving: Optional[bool] = None
    timeouts_taken: Optional[int] = None
    set_history: Optional[Dict[str, int]] = None


class MatchInfoModel(BaseModel):
    model_config = ConfigDict(extra="allow")
    tournament: Optional[str] = None
    phase: Optional[str] = None
    best_of_sets: Optional[int] = None
    current_set: Optional[int] = None
    show_only_current_set: Optional[bool] = None


class OverlayControlModel(BaseModel):
    model_config = ConfigDict(extra="allow")
    show_main_scoreboard: Optional[bool] = None
    show_bottom_ticker: Optional[bool] = None
    ticker_message: Optional[str] = None
    show_player_stats: Optional[bool] = None
    player_stats_data: Optional[Any] = None
    geometry: Optional[Dict[str, Any]] = None
    colors: Optional[Dict[str, str]] = None
    preferredStyle: Optional[str] = None


class OverlayStateUpdate(BaseModel):
    model_config = ConfigDict(extra="allow")
    match_info: Optional[MatchInfoModel] = None
    team_home: Optional[TeamStateModel] = None
    team_away: Optional[TeamStateModel] = None
    overlay_control: Optional[OverlayControlModel] = None
    raw_remote_model: Optional[Any] = None
    raw_remote_customization: Optional[Any] = None


class RawConfigPayload(BaseModel):
    model_config = ConfigDict(extra="allow")
    model: Optional[Any] = None
    customization: Optional[Any] = None


# ---------------------------------------------------------------------------
# Preset themes
# ---------------------------------------------------------------------------

PRESET_THEMES: Dict[str, dict] = {
    "dark": {
        "overlay_control": {
            "colors": {
                "set_bg": "#222222", "set_text": "#FFFFFF",
                "game_bg": "#111111", "game_text": "#FFFFFF",
            }
        }
    },
    "light": {
        "overlay_control": {
            "colors": {
                "set_bg": "#EEEEEE", "set_text": "#222222",
                "game_bg": "#F5F5F5", "game_text": "#111111",
            }
        }
    },
    "esports": {
        "overlay_control": {
            "preferredStyle": "esports",
            "colors": {
                "set_bg": "#0d0d1a", "set_text": "#00FFFF",
                "game_bg": "#0a0a0f", "game_text": "#00FFFF",
            },
        }
    },
    "neo_jersey": {
        "overlay_control": {
            "preferredStyle": "neo_jersey",
        }
    },
    "split_jersey": {
        "overlay_control": {
            "preferredStyle": "split_jersey",
        }
    },
    "clear_jersey": {
        "overlay_control": {
            "preferredStyle": "clear_jersey",
        }
    },
}


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
        request: Request, overlay_id: str, style: str = None
    ):
        resolved = store.resolve_overlay_id(overlay_id)
        if resolved is None:
            raise HTTPException(status_code=404, detail="Overlay ID not found.")
        overlay_id = resolved

        available = store.get_available_styles_list()

        if not style:
            state = await store.load_persisted_state_async(overlay_id)
            preferred = state.get("raw_remote_customization", {}).get(
                "preferredStyle"
            )
            if preferred and preferred in available:
                style = preferred
            else:
                style = "default"

        # Validate style against known templates to prevent path traversal
        if style not in available:
            raise HTTPException(
                status_code=404,
                detail=f"Overlay style '{style}' not found.",
            )

        template_name = "index.html" if style == "default" else f"{style}.html"

        return templates.TemplateResponse(
            request=request,
            name=template_name,
            context={
                "target_id": overlay_id,
                "style": style,
                "v": int(time.time()),
            },
        )

    # -- OBS browser source WebSocket --------------------------------------

    @router.websocket("/ws/{overlay_id}")
    async def obs_websocket(websocket: WebSocket, overlay_id: str):
        resolved = store.resolve_overlay_id(overlay_id)
        if resolved is None:
            await websocket.close(code=4004, reason="Overlay not found")
            return
        overlay_id = resolved
        await websocket.accept()

        broadcast.add_client(overlay_id, websocket)

        try:
            state = store.get_state(overlay_id)
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
        return {"themes": list(PRESET_THEMES.keys())}

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
                    f"Available: {list(PRESET_THEMES.keys())}"
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
