"""ASGI middleware that records HTTP request latency in Prometheus.

Observes one entry per request into ``http_request_duration_seconds``
labelled by ``route`` (the FastAPI route template — bounded by the
OpenAPI surface, never the raw path), ``method`` and ``status``.

WebSocket scopes are skipped: their lifetime is open-ended and does
not map cleanly onto a histogram bucket.

Designed to be cheap when ``prometheus_client`` is missing — every
``observe`` call falls through to a no-op stub in :mod:`app.metrics`
so the middleware can stay wired in unconditionally.
"""
from __future__ import annotations

import time

from app.metrics import http_request_duration_seconds


class MetricsMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.monotonic()
        status_code_holder = {"code": 0}

        async def _send(message):
            if message["type"] == "http.response.start":
                status_code_holder["code"] = int(message.get("status", 0))
            await send(message)

        try:
            await self.app(scope, receive, _send)
        finally:
            elapsed = time.monotonic() - start
            # Resolve the route template so cardinality stays bounded.
            # ``scope['route']`` is set by Starlette once routing has run.
            # When it's missing (404 before routing, lifespan hooks…) we
            # bucket under ``unmatched`` to keep the label cardinality
            # bounded even on a hostile probe storm.
            route_obj = scope.get("route")
            route = getattr(route_obj, "path", None) or "unmatched"
            method = scope.get("method", "UNKNOWN")
            http_request_duration_seconds.labels(
                route=route,
                method=method,
                status=str(status_code_holder["code"] or "0"),
            ).observe(elapsed)
