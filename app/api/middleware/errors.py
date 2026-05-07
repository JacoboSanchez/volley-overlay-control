"""Pure-ASGI middleware that turns unhandled exceptions into logged 500s.

Starlette's default ``ExceptionMiddleware`` already converts uncaught
exceptions to a generic 500 response, but it does so via its own logger
without the request-scoped context. Wrapping the app here lets us log via
the same ``request_id`` / ``oid`` pipeline as the rest of the project,
then re-raise so the framework's own handler still produces the response.

HTTPException is allowed to propagate untouched: it is not an "error" in
the application sense, just a structured response signal.

The log message itself includes the request method, path, exception
class name, and request id, so even text-formatted logs (`LOG_FORMAT=text`)
carry enough context to grep for a specific failure. JSON-formatted
logs additionally surface the same fields under structured keys via
the ``extra`` payload, which makes them queryable in observability
tools without parsing the free-form message.
"""

import logging

from starlette.exceptions import HTTPException as StarletteHTTPException

from app.logging_context import get_request_id

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
        except Exception as exc:
            method = scope.get("method") or scope["type"].upper()
            path = scope.get("path", "<unknown>")
            exc_class = type(exc).__name__
            # ``extra`` keys must not shadow built-in LogRecord
            # attributes (``message``, ``levelname``, …) — we use the
            # ``exc_class`` / ``http_method`` / ``http_path`` prefix
            # so a JSON formatter surfaces them under unambiguous
            # field names.
            logger.exception(
                "Unhandled %s on %s %s — %s (request_id=%s)",
                scope["type"], method, path, exc_class, get_request_id(),
                extra={
                    "exc_class": exc_class,
                    "http_method": method,
                    "http_path": path,
                },
            )
            raise
