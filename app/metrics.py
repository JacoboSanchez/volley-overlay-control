"""Prometheus metrics surface.

Exposes a single ``/metrics`` HTTP endpoint plus a small handful of
counters and gauges that the rest of the codebase bumps from its hot
paths. Designed to degrade gracefully:

* If ``prometheus_client`` is missing (``pip install -r requirements.txt``
  is the canonical fix), ``PROMETHEUS_AVAILABLE`` flips to False and
  every helper becomes a no-op so the operator can still boot the app.
* The ``/metrics`` endpoint stays mounted in either case — when the
  library is missing it returns a 503 with a clear "install
  prometheus-client" message rather than a confusing 404.

Cardinality budget:

* ``http_request_duration_seconds`` — labels ``route``, ``method``,
  ``status``. ``route`` is the FastAPI route template
  (``/api/v1/admin/custom-overlays/{name}``) rather than the raw path,
  so the label set stays bounded by the OpenAPI surface.
* ``webhook_delivery_total`` — labels ``event`` (4 known values)
  and ``status`` (``success`` / ``client_error`` / ``server_error`` /
  ``exception`` / ``dead_letter`` / ``ssrf_blocked``).
* ``ws_clients_total`` and ``ws_oids_active`` — unlabelled gauges so
  a tournament with thousands of OIDs cannot blow up the metric set.
* ``active_sessions`` — unlabelled gauge.

The plan called for ``ws_clients_per_oid``; that label would be
unbounded in OID space and is the textbook anti-pattern. Two
unlabelled gauges (``ws_clients_total`` plus ``ws_oids_active``) give
the operator the same dashboard story (total fan-out + breadth)
without the cardinality risk.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        REGISTRY,
        Counter,
        Gauge,
        Histogram,
        generate_latest,
    )
    PROMETHEUS_AVAILABLE = True
except ImportError:  # pragma: no cover — handled at runtime
    logger.warning(
        "prometheus_client not installed; /metrics will return 503. "
        "Run 'pip install -r requirements.txt' to enable.",
    )
    PROMETHEUS_AVAILABLE = False
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"
    REGISTRY = None  # type: ignore[assignment]

    class _NoOp:
        """Stand-in for missing Counter/Gauge/Histogram/etc.

        Mimics the chainable ``labels(...)`` API so call sites can
        unconditionally do ``METRIC.labels(foo='bar').inc()`` regardless
        of whether the library is present.
        """

        def labels(self, **_kwargs):
            return self

        def inc(self, *_a, **_kw):
            return None

        def dec(self, *_a, **_kw):
            return None

        def set(self, *_a, **_kw):
            return None

        def observe(self, *_a, **_kw):
            return None

        def time(self):  # context manager fallback
            return _NoOpTimer()

    class _NoOpTimer:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    Counter = Gauge = Histogram = _NoOp  # type: ignore[assignment]

    def generate_latest(*_a, **_kw):  # type: ignore[misc]
        return b""


# ---------------------------------------------------------------------------
# Metric definitions
# ---------------------------------------------------------------------------


http_request_duration_seconds = Histogram(
    "voc_http_request_duration_seconds",
    "End-to-end HTTP request latency in seconds.",
    labelnames=("route", "method", "status"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

webhook_delivery_total = Counter(
    "voc_webhook_delivery_total",
    "Webhook delivery outcomes per event and status bucket.",
    labelnames=("event", "status"),
)

ws_clients_total = Gauge(
    "voc_ws_clients_total",
    "Total open frontend WebSocket connections across all OIDs.",
)

ws_oids_active = Gauge(
    "voc_ws_oids_active",
    "Number of distinct OIDs with at least one open WebSocket subscriber.",
)

active_sessions = Gauge(
    "voc_active_sessions",
    "Number of live GameSession instances tracked by SessionManager.",
)


# ---------------------------------------------------------------------------
# Helpers used from hot paths (kept tiny so the bookkeeping cost stays
# under a microsecond when prometheus_client is present and exactly
# zero when it is not).
# ---------------------------------------------------------------------------


def record_webhook_outcome(event: str, status: str) -> None:
    """Increment ``webhook_delivery_total{event, status}`` by 1.

    *status* is one of: ``success``, ``client_error``, ``server_error``,
    ``exception``, ``dead_letter``, ``ssrf_blocked``. Unknown values
    flow through unchanged so a future refinement does not need a
    coordinated metrics change.
    """
    webhook_delivery_total.labels(event=event or "unknown", status=status).inc()


def set_ws_gauges(total_clients: int, oid_count: int) -> None:
    """Refresh the two WebSocket gauges from a single observation."""
    ws_clients_total.set(total_clients)
    ws_oids_active.set(oid_count)


def set_active_sessions(count: int) -> None:
    active_sessions.set(count)
