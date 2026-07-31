"""GET /metrics — Prometheus exposition.

Mounted at the FastAPI app root (not under ``/api/v1``) so the path
matches every other Prometheus-instrumented service the operator is
likely to scrape.

The endpoint remains open by default for backwards-compatible service-mesh
scraping. Operators can set ``METRICS_ENABLED=false`` to hide it or configure
``METRICS_TOKEN`` and send ``Authorization: Bearer <token>``.
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
    refresh_operational_gauges,
)

router = APIRouter()


def _enabled() -> bool:
    return EnvVarsManager.get_bool_env("METRICS_ENABLED", True)


def _required_token() -> str | None:
    value = EnvVarsManager.get_env_var("METRICS_TOKEN", None)
    if value is None:
        return None
    token = str(value).strip()
    return token or None


def _bearer_token(request: Request) -> str | None:
    scheme, separator, value = request.headers.get("authorization", "").partition(" ")
    if not separator or scheme.lower() != "bearer":
        return None
    return value.strip() or None


@router.get(
    "/metrics",
    summary="Prometheus exposition",
    response_class=Response,
)
def metrics_endpoint(request: Request) -> Response:
    """Return the registry's current exposition in Prometheus text format."""
    if not _enabled():
        raise HTTPException(status_code=404, detail="Not Found")
    required_token = _required_token()
    if required_token is not None:
        supplied_token = _bearer_token(request)
        if supplied_token is None or not hmac.compare_digest(
            supplied_token.encode("utf-8"),
            required_token.encode("utf-8"),
        ):
            raise HTTPException(
                status_code=401,
                detail="Invalid metrics bearer token",
                headers={"WWW-Authenticate": 'Bearer realm="metrics"'},
            )
    if not PROMETHEUS_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail=("Metrics disabled: prometheus_client is not installed. Run 'pip install -r requirements.txt' to enable."),
        )
    refresh_operational_gauges()
    body = generate_latest(REGISTRY)
    return Response(content=body, media_type=CONTENT_TYPE_LATEST)
