"""ASGI middleware that populates the request-scoped logging context.

Reads (or generates) an ``X-Request-ID`` header on every HTTP and
WebSocket scope, extracts the ``oid`` query parameter when present, and
stores both in :mod:`app.logging_context` contextvars for the duration
of the request. HTTP responses echo the request id back so callers can
correlate their own logs with ours.
"""

from urllib.parse import parse_qs

from app.logging_context import (
    new_request_id,
    oid_var,
    request_id_var,
)

REQUEST_ID_HEADER = b"x-request-id"


class RequestContextMiddleware:
    """Pure-ASGI middleware: works for both ``http`` and ``websocket`` scopes."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        rid = _extract_request_id(scope) or new_request_id()
        oid = _extract_oid(scope)

        rid_token = request_id_var.set(rid)
        oid_token = oid_var.set(oid or "-")

        async def send_wrapper(message):
            if (
                scope["type"] == "http"
                and message.get("type") == "http.response.start"
            ):
                headers = list(message.get("headers") or [])
                headers.append((REQUEST_ID_HEADER, rid.encode("latin-1")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            request_id_var.reset(rid_token)
            oid_var.reset(oid_token)


def _extract_request_id(scope) -> str | None:
    for key, value in scope.get("headers") or ():
        if key == REQUEST_ID_HEADER:
            return value.decode("latin-1").strip() or None
    return None


def _extract_oid(scope) -> str | None:
    qs = scope.get("query_string") or b""
    if not qs:
        return None
    # latin-1 is total over bytes (never raises) and matches Starlette's
    # own handling of raw ASGI byte strings.
    params = parse_qs(qs.decode("latin-1"), keep_blank_values=False)
    values = params.get("oid")
    return values[0] if values else None
