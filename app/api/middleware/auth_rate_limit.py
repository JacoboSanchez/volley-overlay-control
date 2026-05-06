"""Per-IP rate limiter for authenticated and admin endpoints.

Watches every request whose path matches one of the configured
prefixes; a 401 or 403 response increments the per-IP failure
counter, and once a bucket exceeds ``_MAX_FAILURES`` within
``_WINDOW_SECONDS`` the next request from that IP is short-circuited
with ``429 Too Many Requests`` before reaching the handler.

This guards the four credential-bearing surfaces against brute force:

* ``POST /api/v1/admin/login`` — admin password check.
* ``GET /api/v1/admin/*`` and the rest of the admin CRUD.
* every ``/api/v1/`` route protected by ``verify_api_key``.
* ``/manage`` (admin password used by the static page).

A successful response (anything outside 401/403) clears the bucket
so a legitimate operator who mistyped once isn't penalised.

All state is process-local — clusters with multiple replicas should
front the app with a layer-7 limiter (Cloudflare, Nginx, etc.) that
shares state. The in-process limiter is a defence-in-depth backstop
for self-hosted single-replica deployments.
"""

from __future__ import annotations

import asyncio
import os
import time
from collections import OrderedDict, deque
from typing import Iterable

# Tunables — kept generous so legitimate operator workflows
# (e.g. opening /manage in three tabs) never trip the limit, but
# tight enough that an unattended attacker is throttled within
# seconds. Override via env vars if needed.


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


_MAX_FAILURES = _env_int("AUTH_RATE_LIMIT_MAX_FAILURES", 10)
_WINDOW_SECONDS = float(_env_int("AUTH_RATE_LIMIT_WINDOW_SECONDS", 60))
_BLOCK_SECONDS = float(_env_int("AUTH_RATE_LIMIT_BLOCK_SECONDS", 60))
_MAX_CLIENTS = 4096

# Path prefixes that this limiter watches. Listed explicitly so a future
# unauthenticated route that happens to live under /api/v1/ does not
# silently pull failures from elsewhere into its bucket.
_WATCHED_PREFIXES: tuple[str, ...] = (
    "/api/v1/",
    "/manage",
)


class _Bucket:
    __slots__ = ("failures", "blocked_until")

    def __init__(self) -> None:
        self.failures: deque[float] = deque()
        self.blocked_until: float = 0.0


_buckets: "OrderedDict[str, _Bucket]" = OrderedDict()
_lock = asyncio.Lock()


def _client_ip(scope) -> str:
    """Best-effort peer identifier from the ASGI scope.

    Honours ``X-Forwarded-For`` so the limiter does not collapse every
    caller behind a reverse proxy into one bucket; falls back to the
    raw socket address. Production deployments should also configure
    uvicorn with ``--proxy-headers``.
    """
    for k, v in scope.get("headers") or ():
        if k == b"x-forwarded-for":
            try:
                first = v.decode("latin-1").split(",", 1)[0].strip()
            except Exception:
                first = ""
            if first:
                return first
    client = scope.get("client") or ()
    if isinstance(client, (list, tuple)) and client:
        return str(client[0])
    return "unknown"


def _path_is_watched(path: str, watched: Iterable[str]) -> bool:
    return any(path == p or path.startswith(p) for p in watched)


def _trim_failures_locked(bucket: _Bucket, now: float) -> None:
    cutoff = now - _WINDOW_SECONDS
    while bucket.failures and bucket.failures[0] < cutoff:
        bucket.failures.popleft()


async def _is_blocked(ip: str) -> bool:
    """Return True if the bucket for *ip* is currently blocked."""
    now = time.monotonic()
    async with _lock:
        bucket = _buckets.get(ip)
        if bucket is None:
            return False
        _buckets.move_to_end(ip)
        if bucket.blocked_until > now:
            return True
        return False


async def _record_outcome(ip: str, status_code: int) -> None:
    """Update the bucket for *ip* based on the response *status_code*.

    A 401/403 records a failure (and may flip the bucket into the
    blocked state); any other status drops the bucket entirely so a
    successful login resets the counter.
    """
    now = time.monotonic()
    async with _lock:
        if status_code in (401, 403):
            bucket = _buckets.get(ip)
            if bucket is None:
                bucket = _Bucket()
                _buckets[ip] = bucket
                if len(_buckets) > _MAX_CLIENTS:
                    _buckets.popitem(last=False)
            else:
                _buckets.move_to_end(ip)
            _trim_failures_locked(bucket, now)
            bucket.failures.append(now)
            if len(bucket.failures) >= _MAX_FAILURES:
                bucket.blocked_until = now + _BLOCK_SECONDS
        else:
            # Any non-auth-failure outcome (200, 422, 404, 500, …)
            # clears the bucket. We only care about repeated 401/403.
            _buckets.pop(ip, None)


def _reset_for_tests() -> None:
    """Test hook to clear all buckets between cases."""
    _buckets.clear()


class AuthRateLimitMiddleware:
    """Pure-ASGI middleware enforcing the per-IP failure limit."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "") or ""
        if not _path_is_watched(path, _WATCHED_PREFIXES):
            await self.app(scope, receive, send)
            return

        ip = _client_ip(scope)

        if await _is_blocked(ip):
            await _send_429(send)
            return

        status_holder = {"code": 0}

        async def send_wrapper(message):
            if message.get("type") == "http.response.start":
                status_holder["code"] = int(message.get("status") or 0)
            await send(message)

        await self.app(scope, receive, send_wrapper)
        if status_holder["code"]:
            await _record_outcome(ip, status_holder["code"])


async def _send_429(send) -> None:
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
            (b"retry-after", str(int(_BLOCK_SECONDS)).encode("latin-1")),
            (b"cache-control", b"no-store"),
        ],
    })
    await send({
        "type": "http.response.body",
        "body": body,
        "more_body": False,
    })
