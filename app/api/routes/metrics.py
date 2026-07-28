"""GET /metrics — Prometheus exposition.

Mounted at the FastAPI app root (not under ``/api/v1``) so the path
matches every other Prometheus-instrumented service the operator is
likely to scrape.

**Unauthenticated by default, gateable by configuration.** The exported
metrics are aggregates only — request latency, webhook delivery counts,
total open WebSocket connections, active session count — with no
payloads and no per-OID labels, so the default stays open and a scraper
inside a cluster needs no secret provisioned.

That default is right for a service-mesh scrape and wrong for the
compose file's ``0.0.0.0:80`` bind, where the endpoint is reachable from
the internet. The aggregates are not secrets but they are an oracle:
``voc_active_sessions`` is a logged-in user count, ``voc_ws_oids_active``
is a live-match count, and the per-route latency series enumerate which
routes exist. Two env vars close that off, matching how every other
surface here is gated:

``METRICS_ENABLED=false``
    Removes the endpoint entirely. It answers **404**, not 403 — an
    operator who has switched metrics off wants the endpoint to look
    like it was never mounted, not to advertise that something is here
    behind a gate.

``METRICS_TOKEN=<secret>``
    Requires ``Authorization: Bearer <secret>`` (Prometheus'
    ``authorization`` scrape-config stanza, or ``bearer_token_file``).
    A miss is **401** with a ``WWW-Authenticate`` challenge. Compared
    with :func:`hmac.compare_digest`, like every other credential in
    this codebase.

Both are read per request rather than at import so they can be flipped
through ``REMOTE_CONFIG_URL`` and so tests need no module reload.
"""
from __future__ import annotations

import hmac

from fastapi import APIRouter, HTTPException, Request, Response

from app.env_vars_manager import EnvVarsManager
from app.metrics import (
    CONTENT_TYPE_LATEST,
    PROMETHEUS_AVAILABLE,
    REGISTRY,
    generate_latest,
)

router = APIRouter()

_CHALLENGE = {"WWW-Authenticate": 'Bearer realm="metrics"'}


def _metrics_enabled() -> bool:
    return EnvVarsManager.get_bool_env("METRICS_ENABLED", True)


def _configured_token() -> str | None:
    """Return the configured scrape token, or ``None`` when unset/blank."""
    raw = EnvVarsManager.get_env_var("METRICS_TOKEN", None)
    token = ("" if raw is None else str(raw)).strip()
    return token or None


def _presented_token(request: Request) -> str:
    """Extract the bearer token from the ``Authorization`` header."""
    scheme, _, value = (request.headers.get("authorization") or "").partition(" ")
    if scheme.strip().lower() != "bearer":
        return ""
    return value.strip()


def _authorized(request: Request, expected: str) -> bool:
    # Compare as bytes: hmac.compare_digest rejects str arguments that are
    # not ASCII-only, and a non-ASCII token would otherwise raise TypeError
    # here instead of simply failing to match.
    return hmac.compare_digest(
        _presented_token(request).encode("utf-8"), expected.encode("utf-8"),
    )


@router.get(
    "/metrics",
    summary="Prometheus exposition",
    response_class=Response,
)
def metrics_endpoint(request: Request):
    """Return the registry's current exposition in Prometheus text format."""
    if not _metrics_enabled():
        raise HTTPException(status_code=404, detail="Not Found")
    expected = _configured_token()
    if expected is not None and not _authorized(request, expected):
        raise HTTPException(
            status_code=401,
            detail="Metrics require a valid bearer token.",
            headers=_CHALLENGE,
        )
    if not PROMETHEUS_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail=(
                "Metrics disabled: prometheus_client is not installed. "
                "Run 'pip install -r requirements.txt' to enable."
            ),
        )
    body = generate_latest(REGISTRY)
    return Response(content=body, media_type=CONTENT_TYPE_LATEST)
