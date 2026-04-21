"""Pure-ASGI middleware that turns unhandled exceptions into logged 500s.

Starlette's default ``ExceptionMiddleware`` already converts uncaught
exceptions to a generic 500 response, but it does so via its own logger
without the request-scoped context. Wrapping the app here lets us log via
the same ``request_id`` / ``oid`` pipeline as the rest of the project,
then re-raise so the framework's own handler still produces the response.

HTTPException is allowed to propagate untouched: it is not an "error" in
the application sense, just a structured response signal.
"""

import logging

from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class ExceptionLoggingMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        try:
            await self.app(scope, receive, send)
        except StarletteHTTPException:
            raise
        except Exception:
            logger.exception(
                "Unhandled %s error on %s",
                scope["type"], scope.get("path", "<unknown>"),
            )
            raise
