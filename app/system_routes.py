"""Service worker, PWA manifest, health, and readiness routes."""

from __future__ import annotations

import logging
import os
import tempfile
import time
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

from app.app_config import get_app_title
from app.auth.sessions import COOKIE_NAME
from app.db.engine import get_db
from app.pwa_manifest import (
    _BOARD_TOKEN_RE,
    _board_manifest,
    _render_manifest,
    _with_overlay_shortcuts,
)

logger = logging.getLogger(__name__)


def register_system_routes(
    application: FastAPI,
    frontend_dir: Path,
) -> None:
    """Register runtime/system endpoints before the SPA catch-all."""

    @application.get("/sw.js")
    def serve_sw() -> FileResponse:
        frontend_sw = frontend_dir / "sw.js"
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
        manifest = frontend_dir / "manifest.webmanifest"
        return manifest if manifest.is_file() else None

    @application.get("/manifest.webmanifest")
    def serve_webmanifest(
        request: Request,
        db: Session = Depends(get_db, scope="function"),
    ) -> JSONResponse:
        source = _vite_manifest_path()
        if source is None:
            return JSONResponse(
                {"error": "manifest not available"},
                status_code=404,
            )
        title = get_app_title()
        content = _render_manifest(
            str(source),
            source.stat().st_mtime,
            title,
        )
        username = request.query_params.get("u")
        oid = request.query_params.get("oid")
        if (
            oid
            and _BOARD_TOKEN_RE.match(oid)
            and (not username or _BOARD_TOKEN_RE.match(username))
        ):
            content = _board_manifest(
                content,
                title,
                username or None,
                oid,
            )
        content = _with_overlay_shortcuts(
            content,
            db,
            request.cookies.get(COOKIE_NAME),
        )
        return JSONResponse(
            content=content,
            media_type="application/manifest+json",
            headers={"Cache-Control": "private, no-cache", "Vary": "Cookie"},
        )

    @application.get("/manifest.json")
    def serve_manifest() -> JSONResponse:
        source = _vite_manifest_path()
        if source is None:
            return JSONResponse(
                {"error": "manifest not available"},
                status_code=404,
            )
        return JSONResponse(
            content=_render_manifest(
                str(source),
                source.stat().st_mtime,
                get_app_title(),
            ),
            media_type="application/json",
        )

    @application.get("/health")
    def health_check() -> dict[str, str | int]:
        return {
            "status": "ok",
            "timestamp": int(time.time()),
            "service": "volley-overlay-control",
        }

    @application.get("/health/ready")
    def readiness_check() -> JSONResponse:
        """Readiness probe for writable local persistence."""
        from app.api import action_log

        checks: dict[str, bool] = {}
        reasons: dict[str, str] = {}
        try:
            path = action_log._data_dir()
            os.makedirs(path, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                dir=path,
                prefix=".readiness_probe_",
                delete=True,
            ) as probe:
                probe.write(b"ok")
                probe.flush()
            checks["data_dir_writable"] = True
        except Exception:
            logger.exception("Readiness probe: data dir write failed")
            checks["data_dir_writable"] = False
            reasons["data_dir_writable"] = "write_failed"

        all_ok = all(checks.values())
        payload: dict[str, object] = {
            "status": "ok" if all_ok else "degraded",
            "timestamp": int(time.time()),
            "service": "volley-overlay-control",
            "checks": checks,
        }
        if reasons:
            payload["reasons"] = reasons
        return JSONResponse(payload, status_code=200 if all_ok else 503)
