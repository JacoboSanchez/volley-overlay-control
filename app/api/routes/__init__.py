"""Scoreboard API router assembly.

The original ``app/api/routes.py`` module has been split into domain-specific
submodules. This package re-exports :data:`api_router` and
:data:`router_lifespan` so existing imports (``from app.api.routes import
api_router``) keep working.
"""

from fastapi import APIRouter

from app.api.routes import (
    app_config,
    customization,
    display,
    game,
    overlays,
    session,
    state,
    websocket,
)
from app.api.routes.lifespan import router_lifespan

api_router = APIRouter(
    prefix="/api/v1",
    tags=["Scoreboard API v1"],
    lifespan=router_lifespan,
)

api_router.include_router(app_config.router)
api_router.include_router(session.router)
api_router.include_router(state.router)
api_router.include_router(game.router)
api_router.include_router(display.router)
api_router.include_router(customization.router)
api_router.include_router(overlays.router)
api_router.include_router(websocket.router)

__all__ = ["api_router", "router_lifespan"]
