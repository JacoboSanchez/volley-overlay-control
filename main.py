import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.logging_config import setup_logging
from app.authentication import PasswordAuthenticator, AuthMiddleware
from app.env_vars_manager import EnvVarsManager
from app.api import api_router

# Load environment variables only if tests are not running
if "PYTEST_CURRENT_TEST" not in os.environ:
    load_dotenv()

from app.config_validator import validate_config
validate_config()

setup_logging()
logger = logging.getLogger("Main")

app = FastAPI(title="Volley Overlay Control")

FRONTEND_DIR = Path("frontend/dist")

if PasswordAuthenticator.do_authenticate_users():
    logger.info("User authentication enabled")
    app.add_middleware(AuthMiddleware)

# Mount the REST / WebSocket API
app.include_router(api_router)

# Mount overlay routes (in-process overlay serving for custom overlays)
OVERLAY_TEMPLATES_DIR = Path("overlay_templates")
OVERLAY_STATIC_DIR = Path("overlay_static")

if OVERLAY_TEMPLATES_DIR.is_dir():
    from fastapi.templating import Jinja2Templates
    from app.overlay import overlay_state_store, obs_broadcast_hub
    from app.overlay.routes import create_overlay_router

    _overlay_templates = Jinja2Templates(directory=str(OVERLAY_TEMPLATES_DIR))
    overlay_router = create_overlay_router(
        overlay_state_store, obs_broadcast_hub, _overlay_templates
    )
    app.include_router(overlay_router)
    logger.info("Overlay routes mounted (templates: %s)", OVERLAY_TEMPLATES_DIR)
else:
    logger.warning(
        "Overlay templates directory not found at %s — overlay routes disabled.",
        OVERLAY_TEMPLATES_DIR,
    )

# Serve static assets
app.mount("/fonts", StaticFiles(directory="font"), name="fonts")

if OVERLAY_STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(OVERLAY_STATIC_DIR)), name="overlay-static")

app.mount("/pwa", StaticFiles(directory="app/pwa"), name="pwa")


@app.get("/sw.js")
def serve_sw():
    frontend_sw = FRONTEND_DIR / "sw.js"
    if frontend_sw.is_file():
        return FileResponse(
            frontend_sw,
            media_type="application/javascript",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )
    return FileResponse("app/pwa/sw.js", media_type="application/javascript")


@app.get("/manifest.webmanifest")
def serve_webmanifest():
    manifest = FRONTEND_DIR / "manifest.webmanifest"
    if manifest.is_file():
        return FileResponse(
            manifest,
            media_type="application/manifest+json",
            headers={"Cache-Control": "no-cache"},
        )
    return FileResponse("app/pwa/manifest.json", media_type="application/json")


@app.get("/manifest.json")
def serve_manifest():
    return FileResponse("app/pwa/manifest.json", media_type="application/json")


@app.get("/health")
def health_check():
    import time
    return {
        "status": "ok",
        "timestamp": int(time.time()),
        "service": "volley-overlay-control",
    }


# --- SPA serving (must be LAST — after all API routes and other mounts) ---


class SPAStaticFiles(StaticFiles):
    """StaticFiles with SPA fallback: serves index.html for unknown paths."""

    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except Exception:
            return await super().get_response("index.html", scope)


if FRONTEND_DIR.is_dir():
    if (FRONTEND_DIR / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="spa-assets")
    app.mount("/", SPAStaticFiles(directory=FRONTEND_DIR, html=True), name="spa")
else:
    logger.warning(
        "Frontend build directory not found at %s — SPA will not be served.",
        FRONTEND_DIR,
    )


if __name__ == "__main__":
    import uvicorn

    port = int(EnvVarsManager.get_env_var("APP_PORT", 8080))
    reload = EnvVarsManager.get_env_var("APP_RELOAD", "false").lower() in (
        "yes", "true", "t", "1",
    )

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=reload,
    )
