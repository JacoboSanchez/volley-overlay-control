import logging
import os

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

if PasswordAuthenticator.do_authenticate_users():
    logger.info("User authentication enabled")
    app.add_middleware(AuthMiddleware)

# Mount the REST / WebSocket API
app.include_router(api_router)

# Serve static assets
app.mount("/fonts", StaticFiles(directory="font"), name="fonts")
app.mount("/pwa", StaticFiles(directory="app/pwa"), name="pwa")


@app.get("/sw.js")
def serve_sw():
    return FileResponse("app/pwa/sw.js", media_type="application/javascript")


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
