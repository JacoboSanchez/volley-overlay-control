"""GET /metrics — Prometheus exposition.

Mounted at the FastAPI app root (not under ``/api/v1``) so the path
matches every other Prometheus-instrumented service the operator is
likely to scrape.

The endpoint is **unauthenticated**. The exported metrics expose only
aggregates (request latency, webhook delivery counts, total open
WebSocket connections, active session count) — no payloads, no per-OID
labels — so the surface is safe to scrape from the Kubernetes service
mesh / Prometheus operator without provisioning a secret.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response

from app.metrics import (
    CONTENT_TYPE_LATEST,
    PROMETHEUS_AVAILABLE,
    REGISTRY,
    generate_latest,
)

router = APIRouter()


@router.get(
    "/metrics",
    summary="Prometheus exposition",
    response_class=Response,
)
def metrics_endpoint():
    """Return the registry's current exposition in Prometheus text format."""
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
