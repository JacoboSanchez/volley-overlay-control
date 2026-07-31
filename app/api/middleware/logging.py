"""ASGI middleware that populates the request-scoped logging context.

Reads a bounded ``X-Request-ID`` and W3C ``traceparent`` on every HTTP and
WebSocket scope, extracts the ``oid`` query parameter when present, and
stores them in request-local contextvars. HTTP responses echo the sanitized
request id and this operation's traceparent so participating callers can
correlate their own telemetry with ours.
"""

import re
from urllib.parse import parse_qs

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.logging_context import (
    new_request_id,
    oid_var,
    request_id_var,
)
from app.trace_context import (
    build_trace_context,
    trace_id_var,
    traceparent_var,
    tracestate_var,
)

REQUEST_ID_HEADER = b"x-request-id"
TRACEPARENT_HEADER = b"traceparent"
TRACESTATE_HEADER = b"tracestate"
_MAX_REQUEST_ID_LENGTH = 64
_REQUEST_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,63}\Z")


class RequestContextMiddleware:
    """Pure-ASGI middleware: works for both ``http`` and ``websocket`` scopes."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        trace_context = build_trace_context(
            _extract_header(scope, TRACEPARENT_HEADER),
            _extract_header(scope, TRACESTATE_HEADER),
        )
        rid = _extract_request_id(scope) or (trace_context.trace_id if trace_context.continued else new_request_id())
        oid = _extract_oid(scope)

        rid_token = request_id_var.set(rid)
        oid_token = oid_var.set(oid or "-")
        trace_id_token = trace_id_var.set(trace_context.trace_id)
        traceparent_token = traceparent_var.set(trace_context.traceparent)
        tracestate_token = tracestate_var.set(trace_context.tracestate or "-")

        async def send_wrapper(message: Message) -> None:
            if scope["type"] == "http" and message.get("type") == "http.response.start":
                headers = list(message.get("headers") or [])
                headers.append((REQUEST_ID_HEADER, rid.encode("latin-1")))
                headers.append(
                    (
                        TRACEPARENT_HEADER,
                        trace_context.traceparent.encode("ascii"),
                    )
                )
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            request_id_var.reset(rid_token)
            oid_var.reset(oid_token)
            trace_id_var.reset(trace_id_token)
            traceparent_var.reset(traceparent_token)
            tracestate_var.reset(tracestate_token)


def _extract_request_id(scope: Scope) -> str | None:
    value = _extract_header(scope, REQUEST_ID_HEADER)
    if value is None or len(value) > _MAX_REQUEST_ID_LENGTH or _REQUEST_ID_RE.fullmatch(value) is None:
        return None
    return value


def _extract_header(scope: Scope, target: bytes) -> str | None:
    for key, value in scope.get("headers") or ():
        if key == target:
            if len(value) > 512:
                return None
            try:
                return value.decode("ascii").strip() or None
            except UnicodeDecodeError:
                return None
    return None


def _extract_oid(scope: Scope) -> str | None:
    qs = scope.get("query_string") or b""
    if not qs:
        return None
    # latin-1 is total over bytes (never raises) and matches Starlette's
    # own handling of raw ASGI byte strings.
    params = parse_qs(qs.decode("latin-1"), keep_blank_values=False)
    values = params.get("oid") or params.get("control")
    return values[0] if values else None
