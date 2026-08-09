"""FastAPI application assembly and middleware ordering."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import api_router
from app.api._persistence_paths import data_dir
from app.api.middleware.auth_rate_limit import AuthRateLimitMiddleware
from app.api.middleware.body_limit import BodySizeLimitMiddleware
from app.api.middleware.errors import ExceptionLoggingMiddleware
from app.api.middleware.logging import RequestContextMiddleware
from app.api.middleware.metrics import MetricsMiddleware
from app.api.middleware.security_headers import SecurityHeadersMiddleware
from app.api.routes.metrics import router as metrics_router
from app.auth.bootstrap import ensure_admin_bootstrap
from app.auth.routes import auth_router
from app.db import migrate as db_migrate
from app.error_tracking import configure_error_tracking
from app.match_report import match_report_router
from app.match_report.history import match_history_router
from app.pwa_manifest import _BOARD_TOKEN_RE as _BOARD_TOKEN_RE
from app.pwa_manifest import _board_manifest as _board_manifest
from app.pwa_manifest import _inject_title_into_html as _inject_title_into_html
from app.pwa_manifest import _render_index_html as _render_index_html
from app.pwa_manifest import _render_manifest as _render_manifest
from app.security_bootstrap import run_security_bootstrap
from app.service_errors import ServiceError
from app.static_files import CachedStaticFiles, SPAStaticFiles
from app.system_routes import register_system_routes

logger = logging.getLogger(__name__)

FRONTEND_DIR = Path("frontend/dist")
OVERLAY_TEMPLATES_DIR = Path("overlay_templates")
OVERLAY_STATIC_DIR = Path("overlay_static")


@asynccontextmanager
async def _lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Capture the event loop for background-thread broadcasts."""
    try:
        from app.overlay import obs_broadcast_hub

        obs_broadcast_hub.capture_event_loop()
    except Exception:
        logger.exception("Failed to capture event loop for OBS broadcast hub")
    try:
        from app.api.ws_hub import WSHub

        WSHub.capture_event_loop()
    except Exception:
        logger.exception("Failed to capture event loop for the control WS hub")
    try:
        # Push audit-log rows to control clients over the socket they
        # already hold, so the board stops re-GETting /audit after every
        # point. Installed here (not at import) so a process that only
        # imports the modules — the test suite — keeps the log un-bridged
        # unless it opts in.
        from app.api import audit_broadcast

        audit_broadcast.install()
    except Exception:
        logger.exception("Failed to bridge the audit log onto the control WS hub")
    yield
    try:
        from app.api import audit_broadcast

        audit_broadcast.uninstall()
    except Exception:
        logger.exception("Failed to detach the audit-log WS bridge")


def _register_auth(application: FastAPI) -> None:
    logger.info("Cookie-session authentication enabled")


async def _service_error_response(
    _request: Request,
    exc: Exception,
) -> JSONResponse:
    """Translate caller-safe service errors at the application boundary."""
    assert isinstance(exc, ServiceError)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": str(exc)},
    )


def _register_exception_handlers(application: FastAPI) -> None:
    application.add_exception_handler(ServiceError, _service_error_response)


def _register_api_routes(application: FastAPI) -> None:
    application.include_router(auth_router)
    from app.api.routes.admin_users import router as admin_users_router

    application.include_router(admin_users_router)
    application.include_router(api_router)
    application.include_router(match_report_router)
    application.include_router(match_history_router)
    application.include_router(metrics_router)


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
        overlay_state_store,
        obs_broadcast_hub,
        templates,
    )
    application.include_router(overlay_router)
    logger.info(
        "Overlay routes mounted (templates: %s)",
        OVERLAY_TEMPLATES_DIR,
    )


def _register_static_mounts(application: FastAPI) -> None:
    application.mount(
        "/fonts",
        CachedStaticFiles(
            directory="font",
            cache_control="public, max-age=31536000, immutable",
        ),
        name="fonts",
    )
    if OVERLAY_STATIC_DIR.is_dir():
        application.mount(
            "/static",
            StaticFiles(directory=str(OVERLAY_STATIC_DIR)),
            name="overlay-static",
        )
    application.mount("/pwa", StaticFiles(directory="app/pwa"), name="pwa")

    media_dir = data_dir("media")
    os.makedirs(os.path.join(media_dir, "icons"), exist_ok=True)
    application.mount(
        "/media",
        CachedStaticFiles(
            directory=media_dir,
            cache_control="public, max-age=31536000, immutable",
        ),
        name="media",
    )


def _register_system_endpoints(application: FastAPI) -> None:
    """Compatibility wrapper around the dedicated system route module."""
    register_system_routes(application, FRONTEND_DIR)


def _register_spa(application: FastAPI) -> None:
    """Mount the built SPA as the final catch-all."""
    if not FRONTEND_DIR.is_dir():
        logger.warning(
            "Frontend build directory not found at %s — SPA will not be served.",
            FRONTEND_DIR,
        )
        return
    if (FRONTEND_DIR / "assets").is_dir():
        application.mount(
            "/assets",
            CachedStaticFiles(
                directory=FRONTEND_DIR / "assets",
                cache_control="public, max-age=31536000, immutable",
            ),
            name="spa-assets",
        )
    application.mount(
        "/",
        SPAStaticFiles(directory=FRONTEND_DIR, html=True),
        name="spa",
    )


def _split_csv_env(name: str) -> list[str]:
    """Parse a comma-separated env var into stripped, non-empty items."""
    raw = os.environ.get(name, "")
    return [item.strip() for item in raw.split(",") if item.strip()]


def _maybe_register_trusted_hosts(application: FastAPI) -> None:
    """Enable host validation when ``TRUSTED_HOSTS`` is configured."""
    hosts = _split_csv_env("TRUSTED_HOSTS")
    if not hosts:
        return
    application.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=hosts,
    )
    logger.info(
        "TrustedHostMiddleware enabled (allowed_hosts=%s)",
        ",".join(hosts),
    )


def _maybe_register_cors(application: FastAPI) -> None:
    """Enable credentialed CORS for an explicit origin allow-list."""
    origins = _split_csv_env("CORS_ALLOWED_ORIGINS")
    if not origins:
        return
    if any(origin == "*" for origin in origins):
        logger.error(
            "CORS_ALLOWED_ORIGINS=* is not accepted on a credentialed API — refusing to enable CORS. Use explicit origins."
        )
        return
    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "traceparent",
            "tracestate",
            "X-Client-ID",
            "X-Client-Label",
            "X-Expected-State-Revision",
            "X-Request-ID",
            "Sec-WebSocket-Protocol",
        ],
        # Paginated listings report the full in-scope total here; a
        # cross-origin SPA cannot read it unless it is explicitly exposed.
        expose_headers=[
            "traceparent",
            "X-Request-ID",
            "X-State-Revision",
            "X-Total-Count",
        ],
    )
    logger.info(
        "CORSMiddleware enabled (origins=%s)",
        ",".join(origins),
    )


def create_app() -> FastAPI:
    """Build the application in route/middleware precedence order."""
    configure_error_tracking()
    run_security_bootstrap()
    db_migrate.run_migrations()
    ensure_admin_bootstrap()

    application = FastAPI(
        title="Volley Overlay Control",
        lifespan=_lifespan,
    )
    _register_exception_handlers(application)
    _register_auth(application)
    _register_api_routes(application)
    _register_overlay_routes(application)
    _register_static_mounts(application)
    _register_system_endpoints(application)
    _register_spa(application)

    # Starlette wraps middleware in reverse registration order.
    application.add_middleware(ExceptionLoggingMiddleware)
    application.add_middleware(MetricsMiddleware)
    application.add_middleware(GZipMiddleware, minimum_size=1024)
    application.add_middleware(SecurityHeadersMiddleware)
    application.add_middleware(BodySizeLimitMiddleware)
    application.add_middleware(AuthRateLimitMiddleware)
    _maybe_register_cors(application)
    _maybe_register_trusted_hosts(application)
    # Registered last so request/trace context wraps early responses from
    # TrustedHost, CORS, body-size, and rate-limit middleware too.
    application.add_middleware(RequestContextMiddleware)
    return application
