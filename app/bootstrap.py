"""Application factory.

Exposes :func:`create_app` which returns a fully-wired FastAPI instance.
Keeping assembly in a factory makes it possible to build isolated app
instances in tests (``TestClient(create_app())``) without triggering the
side-effects of module import.
"""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.admin import admin_page_router, admin_router
from app.api import api_router
from app.authentication import AuthMiddleware, PasswordAuthenticator

logger = logging.getLogger("Bootstrap")


FRONTEND_DIR = Path("frontend/dist")
OVERLAY_TEMPLATES_DIR = Path("overlay_templates")
OVERLAY_STATIC_DIR = Path("overlay_static")


class SPAStaticFiles(StaticFiles):
    """StaticFiles with SPA fallback: serves index.html for unknown paths."""

    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except Exception:
            return await super().get_response("index.html", scope)


@asynccontextmanager
async def _lifespan(application: FastAPI):
    """Capture the running event loop so background threads can schedule tasks."""
    try:
        from app.overlay import obs_broadcast_hub
        obs_broadcast_hub.capture_event_loop()
    except Exception:
        pass
    yield


def _register_auth(application: FastAPI) -> None:
    if PasswordAuthenticator.do_authenticate_users():
        logger.info("User authentication enabled")
        application.add_middleware(AuthMiddleware)


def _register_api_routes(application: FastAPI) -> None:
    application.include_router(api_router)
    # Overlay manager page + admin API (password-protected).
    # Registered before the SPA mount so ``/manage`` is served by FastAPI.
    application.include_router(admin_page_router)
    application.include_router(admin_router)


def _register_overlay_routes(application: FastAPI) -> None:
    if not OVERLAY_TEMPLATES_DIR.is_dir():
        logger.warning(
            "Overlay templates directory not found at %s — overlay routes disabled.",
            OVERLAY_TEMPLATES_DIR,
        )
        return

    from fastapi.templating import Jinja2Templates
    from app.overlay import obs_broadcast_hub, overlay_state_store
    from app.overlay.routes import create_overlay_router

    templates = Jinja2Templates(directory=str(OVERLAY_TEMPLATES_DIR))
    overlay_router = create_overlay_router(
        overlay_state_store, obs_broadcast_hub, templates
    )
    application.include_router(overlay_router)
    logger.info("Overlay routes mounted (templates: %s)", OVERLAY_TEMPLATES_DIR)


def _register_static_mounts(application: FastAPI) -> None:
    application.mount("/fonts", StaticFiles(directory="font"), name="fonts")
    if OVERLAY_STATIC_DIR.is_dir():
        application.mount(
            "/static",
            StaticFiles(directory=str(OVERLAY_STATIC_DIR)),
            name="overlay-static",
        )
    application.mount("/pwa", StaticFiles(directory="app/pwa"), name="pwa")


def _register_system_endpoints(application: FastAPI) -> None:
    @application.get("/sw.js")
    def serve_sw():
        frontend_sw = FRONTEND_DIR / "sw.js"
        if frontend_sw.is_file():
            return FileResponse(
                frontend_sw,
                media_type="application/javascript",
                headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
            )
        return FileResponse("app/pwa/sw.js", media_type="application/javascript")

    @application.get("/manifest.webmanifest")
    def serve_webmanifest():
        manifest = FRONTEND_DIR / "manifest.webmanifest"
        if manifest.is_file():
            return FileResponse(
                manifest,
                media_type="application/manifest+json",
                headers={"Cache-Control": "no-cache"},
            )
        return FileResponse("app/pwa/manifest.json", media_type="application/json")

    @application.get("/manifest.json")
    def serve_manifest():
        return FileResponse("app/pwa/manifest.json", media_type="application/json")

    @application.get("/health")
    def health_check():
        import time
        return {
            "status": "ok",
            "timestamp": int(time.time()),
            "service": "volley-overlay-control",
        }


def _register_spa(application: FastAPI) -> None:
    """Mount the built SPA as the catch-all. Must be called last."""
    if not FRONTEND_DIR.is_dir():
        logger.warning(
            "Frontend build directory not found at %s — SPA will not be served.",
            FRONTEND_DIR,
        )
        return

    if (FRONTEND_DIR / "assets").is_dir():
        application.mount(
            "/assets",
            StaticFiles(directory=FRONTEND_DIR / "assets"),
            name="spa-assets",
        )
    application.mount(
        "/",
        SPAStaticFiles(directory=FRONTEND_DIR, html=True),
        name="spa",
    )


def create_app() -> FastAPI:
    """Build and return the FastAPI application.

    Route registration order matters: system endpoints and routers must be
    registered before the SPA catch-all mount, otherwise the SPA consumes
    every unmatched path.
    """
    application = FastAPI(title="Volley Overlay Control", lifespan=_lifespan)
    _register_auth(application)
    _register_api_routes(application)
    _register_overlay_routes(application)
    _register_static_mounts(application)
    _register_system_endpoints(application)
    _register_spa(application)
    return application
