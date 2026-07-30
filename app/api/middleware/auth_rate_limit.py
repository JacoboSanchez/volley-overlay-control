"""Per-IP failure limiter for credential-bearing and capability-token routes.

Watches every HTTP request whose path matches a configured surface. A
response whose status is one of that surface's *failure statuses*
increments the per-(surface, IP) counter, and once a bucket exceeds
``AUTH_RATE_LIMIT_MAX_FAILURES`` within ``AUTH_RATE_LIMIT_WINDOW_SECONDS``
the next matching request from that IP is short-circuited with
``429 Too Many Requests`` before reaching the handler.

Two surfaces are watched, with **separate keyspaces**:

``api``
    ``/api/v1/*`` — the cookie-session and admin CRUD routes. Failures are
    401/403: an explicit authorization refusal.

``capability``
    ``/overlay/*``, ``/follow/*`` and ``/match/*`` — addressed by an
    unguessable token rather than a session. A wrong token here surfaces as
    **404** (`app/overlay/routes.py`) or 401 (`app/match_report_access.py`),
    so this surface counts 401/403/404. Before this existed, token guessing
    incremented nothing at all: the limiter only watched ``/api/v1/`` and
    only counted 401/403.

Keying buckets on ``(surface, ip)`` rather than ``ip`` alone is the
load-bearing detail. A single shared bucket would mean that widening the
watched set could take an on-air ``/overlay/`` browser source off the air
because somebody's SPA collected 403s against ``/api/v1/`` — trading a
brute-force risk for an availability one. With split keyspaces a surface
can only throttle itself.

A successful response is intentionally ignored — the bucket is reset only
by the sliding window expiring old failures. This prevents an attacker
from laundering failed login attempts by interleaving them with hits to a
public endpoint under the same prefix. See ``_record_outcome``.

Deliberately **not** watched:

``/ws/*`` and the control WebSocket
    A WebSocket handshake arrives as ASGI scope type ``websocket``, not
    ``http``, so this middleware structurally cannot observe it. Listing
    the prefix would imply protection that does not exist.

``/media/**``
    Carries no credential — its filenames embed a content hash. The
    exposure there is request *volume*, which a failure-based limiter does
    nothing about, while counting its 404s would risk blocking a venue's
    icons after an ordinary delete. Volume limiting belongs at the proxy.

``/metrics``
    The concern there is that it is unauthenticated, not that it is
    brute-forceable. Tracked separately.

All state is process-local — clusters with multiple replicas should front
the app with a layer-7 limiter (Cloudflare, Nginx, etc.) that shares
state. This is a defence-in-depth backstop for self-hosted single-replica
deployments. Note also that a per-IP limiter cannot distinguish several
operators behind one NAT from a single attacker; the split keyspaces bound
the blast radius, and ``voc_rate_limit_blocks_total`` makes a lockout
visible, but the tradeoff is inherent to keying on IP.
"""

from __future__ import annotations

import asyncio
import os
import time
from collections import OrderedDict, deque
from collections.abc import Iterable

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_MAX_CLIENTS = 4096

# Surface name -> (watched path prefixes, statuses that count as a failure).
#
# Listed explicitly rather than derived, so a future unauthenticated route
# that happens to live under a watched prefix does not silently pull
# failures from elsewhere into its bucket.
_API_SURFACE = "api"
_CAPABILITY_SURFACE = "capability"

_SURFACES: tuple[tuple[str, tuple[str, ...], frozenset[int]], ...] = (
    (_API_SURFACE, ("/api/v1/",), frozenset({401, 403})),
    (
        _CAPABILITY_SURFACE,
        ("/overlay/", "/follow/", "/match/"),
        # 404 included: an unknown capability token is reported as "not
        # found", so it is the only signal a guessing attempt produces.
        frozenset({401, 403, 404}),
    ),
)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


# Read per call rather than at import. The tunables are documented as env
# overrides, but evaluating them at import time meant they only applied if
# the variable was set before this module was first imported — which made
# them a footgun in tests and in embedded use, and forced the test suite to
# ``importlib.reload`` this module to change a limit. os.environ lookups are
# dict hits, and these are only consulted on a failure or a block.
def _max_failures() -> int:
    return _env_int("AUTH_RATE_LIMIT_MAX_FAILURES", 10)


def _window_seconds() -> float:
    return float(_env_int("AUTH_RATE_LIMIT_WINDOW_SECONDS", 60))


def _block_seconds() -> float:
    return float(_env_int("AUTH_RATE_LIMIT_BLOCK_SECONDS", 60))


class _Bucket:
    __slots__ = ("blocked_until", "failures")

    def __init__(self) -> None:
        self.failures: deque[float] = deque()
        self.blocked_until: float = 0.0


# Keyed by (surface, ip) — see the module docstring for why the surface is
# part of the key.
_buckets: OrderedDict[tuple[str, str], _Bucket] = OrderedDict()
_lock = asyncio.Lock()


def _client_ip(scope: Scope) -> str:
    """Best-effort peer identifier from the ASGI scope.

    Reads ``scope["client"]`` only — uvicorn populates this from the
    socket peer by default, and from a trusted proxy hop when the
    server is started with ``--proxy-headers`` /
    ``--forwarded-allow-ips``. Trusting ``X-Forwarded-For`` directly
    here would be spoofable: any request can supply that header and
    pin the leftmost value to an arbitrary IP, defeating the
    per-IP bucket. The ASGI server is the single trust boundary that
    decides whether the proxy chain is honoured.

    Operators behind a reverse proxy must configure uvicorn /
    gunicorn with the appropriate proxy-header flags so
    ``scope["client"]`` reflects the real remote IP — see
    `AUTHENTICATION.md` §6 for guidance.
    """
    client = scope.get("client") or ()
    if isinstance(client, (list, tuple)) and client:
        return str(client[0])
    return "unknown"


def _path_is_watched(path: str, watched: Iterable[str]) -> bool:
    return any(path == p or path.startswith(p) for p in watched)


def _resolve_surface(path: str) -> tuple[str, frozenset[int]] | None:
    """Return the ``(surface, failure_statuses)`` watching *path*, if any."""
    for name, prefixes, failure_statuses in _SURFACES:
        if _path_is_watched(path, prefixes):
            return name, failure_statuses
    return None


def _trim_failures_locked(bucket: _Bucket, now: float, window: float) -> None:
    cutoff = now - window
    while bucket.failures and bucket.failures[0] < cutoff:
        bucket.failures.popleft()


async def _is_blocked(key: tuple[str, str]) -> bool:
    """Return True if the bucket for *key* is currently blocked."""
    now = time.monotonic()
    async with _lock:
        bucket = _buckets.get(key)
        if bucket is None:
            return False
        _buckets.move_to_end(key)
        return bucket.blocked_until > now


async def _record_outcome(
    key: tuple[str, str], status_code: int, failure_statuses: frozenset[int],
) -> None:
    """Update the bucket for *key* based on the response *status_code*.

    A status in *failure_statuses* appends a failure timestamp (and may flip
    the bucket into the blocked state). Any other status is ignored: an
    attacker can hit unauthenticated endpoints under the same prefix to draw
    a 200, so "200 clears the bucket" would let them launder failures and
    bypass the limit. The sliding window already evicts old failures once
    they fall out of the window, which is the only legitimate reset path.
    """
    if status_code not in failure_statuses:
        return
    now = time.monotonic()
    async with _lock:
        bucket = _buckets.get(key)
        if bucket is None:
            bucket = _Bucket()
            _buckets[key] = bucket
            if len(_buckets) > _MAX_CLIENTS:
                _buckets.popitem(last=False)
        else:
            _buckets.move_to_end(key)
        _trim_failures_locked(bucket, now, _window_seconds())
        bucket.failures.append(now)
        if len(bucket.failures) >= _max_failures():
            bucket.blocked_until = now + _block_seconds()


def _reset_for_tests() -> None:
    """Test hook to clear all buckets between cases."""
    _buckets.clear()


class AuthRateLimitMiddleware:
    """Pure-ASGI middleware enforcing the per-(surface, IP) failure limit."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        # WebSocket handshakes arrive as scope type "websocket" and are not
        # observable here — see the module docstring.
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        resolved = _resolve_surface(scope.get("path", "") or "")
        if resolved is None:
            await self.app(scope, receive, send)
            return
        surface, failure_statuses = resolved

        key = (surface, _client_ip(scope))

        if await _is_blocked(key):
            _record_block(surface)
            await _send_429(send)
            return

        status_holder = {"code": 0}

        async def send_wrapper(message: Message) -> None:
            if message.get("type") == "http.response.start":
                status_holder["code"] = int(message.get("status") or 0)
            await send(message)

        await self.app(scope, receive, send_wrapper)
        if status_holder["code"]:
            await _record_outcome(key, status_holder["code"], failure_statuses)


def _record_block(surface: str) -> None:
    """Count the 429 without letting a metrics problem break the refusal."""
    try:
        from app.metrics import record_rate_limit_block

        record_rate_limit_block(surface)
    except Exception:  # pragma: no cover - defensive
        pass


async def _send_429(send: Send) -> None:
    body = (
        b'{"detail":"Too many authentication failures. '
        b'Please retry later."}'
    )
    await send({
        "type": "http.response.start",
        "status": 429,
        "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode("latin-1")),
            (b"retry-after", str(int(_block_seconds())).encode("latin-1")),
            (b"cache-control", b"no-store"),
        ],
    })
    await send({
        "type": "http.response.body",
        "body": body,
        "more_body": False,
    })
