"""Static-file response policies used by the application factory."""

from __future__ import annotations

from pathlib import Path

from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.app_config import get_app_title
from app.pwa_manifest import _render_index_html


class SPAStaticFiles(StaticFiles):
    """Serve the SPA shell for unknown paths and rewrite its runtime title."""

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
        if self.directory is None:
            return await super().get_response("index.html", scope)
        index_path = Path(self.directory) / "index.html"
        if not index_path.is_file():
            return await super().get_response("index.html", scope)
        rewritten = _render_index_html(
            str(index_path),
            index_path.stat().st_mtime,
            get_app_title(),
        )
        return HTMLResponse(
            rewritten,
            headers={"Cache-Control": "no-cache, must-revalidate"},
        )


class CachedStaticFiles(StaticFiles):
    """Apply a shared cache policy to successful static-file responses."""

    def __init__(self, *args, cache_control: str, **kwargs):
        super().__init__(*args, **kwargs)
        self._cache_control = cache_control

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        if response.status_code in (200, 206, 304):
            response.headers.setdefault("Cache-Control", self._cache_control)
        return response
