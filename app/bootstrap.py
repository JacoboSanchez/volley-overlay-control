"""Application factory.

Exposes :func:`create_app` which returns a fully-wired FastAPI instance.
Keeping assembly in a factory makes it possible to build isolated app
instances in tests (``TestClient(create_app())``) without triggering the
side-effects of module import.
"""

import html
import json
import logging
import os
import re
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.admin import admin_page_router, admin_router
from app.api import api_router
from app.app_config import get_app_title
from app.authentication import PasswordAuthenticator

logger = logging.getLogger("Bootstrap")


FRONTEND_DIR = Path("frontend/dist")
OVERLAY_TEMPLATES_DIR = Path("overlay_templates")
OVERLAY_STATIC_DIR = Path("overlay_static")


# Matches the first ``<title>`` element, including any attributes
# (e.g. ``<title lang="en">``).
_TITLE_PATTERN = re.compile(
    r"<title(?:\s+[^>]*)?>.*?</title>", re.IGNORECASE | re.DOTALL,
)


def _inject_title_into_html(html_content: str, title: str) -> str:
    """Replace the first ``<title>...</title>`` with the escaped *title*."""
    return _TITLE_PATTERN.sub(
        f"<title>{html.escape(title)}</title>", html_content, count=1,
    )


@lru_cache(maxsize=8)
def _render_index_html(path: str, mtime: float, title: str) -> str:
    """Memoize the rewritten ``index.html``.

    Cache key includes ``mtime`` so a rebuilt frontend invalidates the
    entry, and ``title`` so a changed ``APP_TITLE`` (e.g. via remote config)
    is reflected without a restart.
    """
    text = Path(path).read_text(encoding="utf-8")
    return _inject_title_into_html(text, title)


@lru_cache(maxsize=8)
def _render_manifest(path: str, mtime: float, title: str) -> dict:
    """Memoize the rewritten PWA manifest. See :func:`_render_index_html`."""
    with Path(path).open("r", encoding="utf-8") as f:
        data = json.load(f)
    data["name"] = title
    data["short_name"] = title
    return data


class SPAStaticFiles(StaticFiles):
    """StaticFiles with SPA fallback: serves index.html for unknown paths.

    The served ``index.html`` has its ``<title>`` rewritten to the value of
    the ``APP_TITLE`` env var so the browser tab matches the configured app
    name without rebuilding the frontend. The rewritten HTML is memoized
    by ``(path, mtime, title)`` so steady-state requests do no disk I/O
    beyond a single ``stat()``.
    """

    async def get_response(self, path, scope):
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404:
                return await self._index_response(scope)
            raise
        if path in ("", "index.html"):
            return await self._index_response(scope)
        return response

    async def _index_response(self, scope):
        index_path = Path(self.directory) / "index.html"
        if not index_path.is_file():
            return await super().get_response("index.html", scope)
        rewritten = _render_index_html(
            str(index_path), index_path.stat().st_mtime, get_app_title(),
        )
        return HTMLResponse(rewritten)


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

    if not os.environ.get("OVERLAY_SERVER_TOKEN", "").strip():
        logger.warning(
            "OVERLAY_SERVER_TOKEN is not set — overlay server mutation "
            "and config endpoints are unauthenticated. See "
            "AUTHENTICATION.md (F-3, F-5) for details."
        )


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
        # The service worker is generated by vite-plugin-pwa into the frontend
        # build output. No runtime fallback: without a frontend build there is
        # no SPA to serve either, and a legacy hand-written worker would race
        # with the workbox-generated one for the /sw.js scope.
        frontend_sw = FRONTEND_DIR / "sw.js"
        if not frontend_sw.is_file():
            raise HTTPException(
                status_code=404,
                detail="Service worker not available (frontend build missing).",
            )
        return FileResponse(
            frontend_sw,
            media_type="application/javascript",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    def _vite_manifest_path() -> Path | None:
        """Return the Vite-generated manifest if the frontend was built."""
        manifest = FRONTEND_DIR / "manifest.webmanifest"
        return manifest if manifest.is_file() else None

    @application.get("/manifest.webmanifest")
    def serve_webmanifest():
        source = _vite_manifest_path()
        if source is None:
            return JSONResponse({"error": "manifest not available"}, status_code=404)
        return JSONResponse(
            content=_render_manifest(str(source), source.stat().st_mtime, get_app_title()),
            media_type="application/manifest+json",
            headers={"Cache-Control": "no-cache"},
        )

    @application.get("/manifest.json")
    def serve_manifest():
        # Legacy alias for /manifest.webmanifest. Description omitted to avoid
        # OpenAPI schema drift; a docstring would surface as "description" and
        # require regenerating frontend/src/api/schema.d.ts.
        source = _vite_manifest_path()
        if source is None:
            return JSONResponse({"error": "manifest not available"}, status_code=404)
        return JSONResponse(
            content=_render_manifest(str(source), source.stat().st_mtime, get_app_title()),
            media_type="application/json",
        )

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
