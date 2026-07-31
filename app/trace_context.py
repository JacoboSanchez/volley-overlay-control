"""Bounded W3C Trace Context parsing and request-local propagation.

The application does not require a tracing vendor, but it still participates
in the vendor-neutral ``traceparent`` protocol:

* valid version-00 parents keep their trace id and receive a fresh span id;
* invalid or missing parents start a new trace;
* ``tracestate`` is forwarded only with a valid parent and is bounded to the
  W3C 512-character limit;
* outbound HTTP helpers can read the current context without threading values
  through every call.
"""

from __future__ import annotations

import contextvars
import re
import secrets
from dataclasses import dataclass

_TRACEPARENT_V00_RE = re.compile(r"00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})\Z")
_SIMPLE_TRACESTATE_KEY_RE = re.compile(r"[a-z][a-z0-9_\-*/]{0,255}\Z")
_MULTI_TENANT_TRACESTATE_KEY_RE = re.compile(
    r"[a-z0-9][a-z0-9_\-*/]{0,240}@[a-z][a-z0-9_\-*/]{0,13}\Z"
)
_ZERO_TRACE_ID = "0" * 32
_ZERO_PARENT_ID = "0" * 16
_MAX_TRACESTATE_LENGTH = 512
_MAX_TRACESTATE_MEMBERS = 32

trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "trace_id",
    default="-",
)
traceparent_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "traceparent",
    default="-",
)
tracestate_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "tracestate",
    default="-",
)


@dataclass(frozen=True, slots=True)
class TraceContext:
    """Validated context for the server operation handling one request."""

    trace_id: str
    traceparent: str
    tracestate: str | None
    continued: bool


def _parse_traceparent(value: str | None) -> tuple[str, str] | None:
    """Return ``(trace_id, flags)`` for a valid W3C version-00 parent."""
    if value is None or len(value) != 55:
        return None
    match = _TRACEPARENT_V00_RE.fullmatch(value)
    if match is None:
        return None
    trace_id, parent_id, flags = match.groups()
    if trace_id == _ZERO_TRACE_ID or parent_id == _ZERO_PARENT_ID:
        return None
    # Version 00 defines only the sampled bit. Clear client-supplied reserved
    # bits before forwarding so they cannot acquire accidental semantics.
    sampled_flag = int(flags, 16) & 0x01
    return trace_id, f"{sampled_flag:02x}"


def _bounded_tracestate(value: str | None) -> str | None:
    if value is None:
        return None
    candidate = value.strip()
    if not candidate or len(candidate) > _MAX_TRACESTATE_LENGTH:
        return None
    if any(ord(char) < 0x20 or ord(char) > 0x7E for char in candidate):
        return None
    members = [member.strip() for member in candidate.split(",")]
    if len(members) > _MAX_TRACESTATE_MEMBERS:
        return None
    seen_keys: set[str] = set()
    for member in members:
        key, separator, member_value = member.partition("=")
        valid_key = (
            _SIMPLE_TRACESTATE_KEY_RE.fullmatch(key) is not None
            or _MULTI_TENANT_TRACESTATE_KEY_RE.fullmatch(key) is not None
        )
        valid_value = (
            bool(separator)
            and 1 <= len(member_value) <= 256
            and member_value[-1] != " "
            and "," not in member_value
            and "=" not in member_value
        )
        if not valid_key or not valid_value or key in seen_keys:
            return None
        seen_keys.add(key)
    return candidate


def build_trace_context(
    incoming_traceparent: str | None,
    incoming_tracestate: str | None = None,
) -> TraceContext:
    """Validate an incoming parent and create this server operation's span."""
    parsed = _parse_traceparent(incoming_traceparent)
    if parsed is None:
        trace_id = secrets.token_hex(16)
        flags = "00"
        tracestate = None
        continued = False
    else:
        trace_id, flags = parsed
        tracestate = _bounded_tracestate(incoming_tracestate)
        continued = True
    span_id = secrets.token_hex(8)
    return TraceContext(
        trace_id=trace_id,
        traceparent=f"00-{trace_id}-{span_id}-{flags}",
        tracestate=tracestate,
        continued=continued,
    )


def get_trace_id() -> str:
    return trace_id_var.get()


def outbound_trace_headers() -> dict[str, str]:
    """Return the current W3C headers for an outbound request, if any."""
    traceparent = traceparent_var.get()
    if traceparent == "-":
        return {}
    headers = {"traceparent": traceparent}
    tracestate = tracestate_var.get()
    if tracestate != "-":
        headers["tracestate"] = tracestate
    return headers
