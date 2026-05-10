"""GET /metrics — Prometheus exposition.

Mounted at the FastAPI app root (not under ``/api/v1``) so the path
matches every other Prometheus-instrumented service the operator is
likely to scrape.

Auth ladder:

* Default: **unauthenticated**. The exported metrics expose
  aggregates (request latency, webhook delivery counts, total open
  WebSocket connections, active session count) — no payloads, no
  per-OID labels — so the surface is safe to scrape from the
  Kubernetes service mesh / Prometheus operator without provisioning
  another secret.
* Opt-in: setting ``METRICS_REQUIRE_ADMIN=true`` gates the route
  behind the same Bearer token as ``/api/v1/admin/*`` for operators
  who would rather not expose anything to the LAN.
"""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Response

from app.auth_utils import require_admin_token
from app.env_vars_manager import EnvVarsManager
from app.metrics import (
    CONTENT_TYPE_LATEST,
    PROMETHEUS_AVAILABLE,
    REGISTRY,
    generate_latest,
)

router = APIRouter()


def _require_admin_when_configured() -> bool:
    return EnvVarsManager.get_bool_env("METRICS_REQUIRE_ADMIN")


@router.get(
    "/metrics",
    summary="Prometheus exposition",
    response_class=Response,
)
def metrics_endpoint(authorization: str = Header(None)):
    """Return the registry's current exposition in Prometheus text format.

    ``METRICS_REQUIRE_ADMIN=true`` opts into Bearer auth at the same
    ladder as ``/api/v1/admin/*``. The check fires *before* the
    library-availability check so an unauthenticated probe cannot use
    the 503-vs-200 difference to fingerprint whether the metrics
    backend is loaded.
    """
    if _require_admin_when_configured():
        require_admin_token(
            authorization,
            token=None,
            missing_password_detail=(  # nosec B106
                "Metrics auth requested but OVERLAY_MANAGER_PASSWORD is unset."
            ),
            missing_token_detail=(  # nosec B106
                "Missing admin password. Use 'Authorization: Bearer <password>'."
            ),
            invalid_token_detail="Invalid admin password.",  # nosec B106
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
