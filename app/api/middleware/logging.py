"""ASGI middleware that populates the request-scoped logging context.

Reads (or generates) an ``X-Request-ID`` header on every HTTP and
WebSocket scope, extracts the ``oid`` query parameter when present, and
stores both in :mod:`app.logging_context` contextvars for the duration
of the request. HTTP responses echo the request id back so callers can
correlate their own logs with ours.

Two properties of the inbound request id are load-bearing:

*Bounded.* The id is echoed into a response header **and** interpolated
into every log line emitted for the request, so an unvalidated one is a
log-inflation primitive: a single multi-kilobyte header would be written
back out once per record. Anything that is not a short, printable token
(:data:`_REQUEST_ID_RE`) is discarded in favour of a generated id rather
than truncated — a truncated id no longer matches what the caller logged,
so it buys nothing over a fresh one while still letting the caller pick
the log content.

*Interoperable.* When the caller sends no ``X-Request-ID`` but does send
a well-formed W3C ``traceparent`` (a proxy, a service mesh, or an
OpenTelemetry-instrumented upstream), its trace-id becomes our request
id, so our logs join the caller's trace instead of inventing a parallel
correlation id for the same request. An explicit ``X-Request-ID`` still
wins — it is the more specific signal. Either way the trace-id, when
present, also lands in its own contextvar so it can be logged and
attached to error reports.
"""

import re
from urllib.parse import parse_qs

from app.logging_context import (
    new_request_id,
    oid_var,
    request_id_var,
    trace_id_var,
)

REQUEST_ID_HEADER = b"x-request-id"
TRACEPARENT_HEADER = b"traceparent"

# Upper bound on an accepted inbound request id. Long enough for a UUID
# (36), a hex UUID (32), a 32-hex trace-id, or a proxy's own compound id;
# short enough that echoing it per log record costs nothing.
MAX_REQUEST_ID_LEN = 64
# What the contextvars hold when nothing was supplied. Never a valid
# inbound value: the formatters read it as "omit the context block".
CONTEXT_SENTINEL = "-"
# Deliberately narrow: the characters every request-id convention we care
# about (uuid4, hex, nginx/Envoy ids, trace-ids) actually uses. Keeping
# the set to ASCII also makes the latin-1 encode on the response path
# total, and leaves no room for the CR/LF that a header-splitting attempt
# would need.
_REQUEST_ID_RE = re.compile(r"\A[A-Za-z0-9._-]+\Z")

# W3C Trace Context ``traceparent``: ``<version>-<trace-id>-<parent-id>-<flags>``
# in lowercase hex. Version ``ff`` is reserved/invalid, the all-zero
# trace-id and parent-id are invalid, and version ``00`` is exactly four
# fields — later versions may append more, which a forward-compatible
# parser is required to tolerate.
_HEX2_RE = re.compile(r"\A[0-9a-f]{2}\Z")
_HEX16_RE = re.compile(r"\A[0-9a-f]{16}\Z")
_HEX32_RE = re.compile(r"\A[0-9a-f]{32}\Z")


class RequestContextMiddleware:
    """Pure-ASGI middleware: works for both ``http`` and ``websocket`` scopes."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        trace_id = _extract_trace_id(scope)
        rid = _extract_request_id(scope) or trace_id or new_request_id()
        oid = _extract_oid(scope)

        rid_token = request_id_var.set(rid)
        oid_token = oid_var.set(oid or CONTEXT_SENTINEL)
        trace_token = trace_id_var.set(trace_id or CONTEXT_SENTINEL)

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
            trace_id_var.reset(trace_token)


def _header(scope, name: bytes) -> str | None:
    for key, value in scope.get("headers") or ():
        if key == name:
            # latin-1 is total over bytes (never raises) and matches
            # Starlette's own handling of raw ASGI byte strings.
            return value.decode("latin-1")
    return None


def _extract_request_id(scope) -> str | None:
    """Return the caller's request id, or ``None`` to mint a fresh one.

    Rejects (rather than repairs) anything oversized or outside the
    allowed character set — see the module docstring.
    """
    raw = _header(scope, REQUEST_ID_HEADER)
    if raw is None:
        return None
    candidate = raw.strip()
    if not candidate or len(candidate) > MAX_REQUEST_ID_LEN:
        return None
    # "-" is the contextvar sentinel for "no request id", which the text
    # formatter reads as "omit the context block". Accepting it verbatim
    # would let a caller suppress its own request's correlation output.
    if candidate == CONTEXT_SENTINEL:
        return None
    if not _REQUEST_ID_RE.match(candidate):
        return None
    return candidate


def _extract_trace_id(scope) -> str | None:
    """Return the trace-id from a valid inbound ``traceparent``, else ``None``."""
    raw = _header(scope, TRACEPARENT_HEADER)
    if raw is None:
        return None
    parts = raw.strip().split("-")
    if len(parts) < 4:
        return None
    version, trace_id, parent_id, flags = parts[:4]
    if version == "00" and len(parts) != 4:
        return None
    if not _HEX2_RE.match(version) or version == "ff":
        return None
    if not _HEX32_RE.match(trace_id) or trace_id == "0" * 32:
        return None
    if not _HEX16_RE.match(parent_id) or parent_id == "0" * 16:
        return None
    if not _HEX2_RE.match(flags):
        return None
    return trace_id


def _extract_oid(scope) -> str | None:
    qs = scope.get("query_string") or b""
    if not qs:
        return None
    # latin-1 is total over bytes (never raises) and matches Starlette's
    # own handling of raw ASGI byte strings.
    params = parse_qs(qs.decode("latin-1"), keep_blank_values=False)
    values = params.get("oid") or params.get("control")
    return values[0] if values else None
