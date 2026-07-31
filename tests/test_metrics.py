"""Tests for the Prometheus exposition surface (M15)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.bootstrap import create_app

pytestmark = pytest.mark.usefixtures("clean_sessions")


@pytest.fixture(autouse=True)
def _metrics_defaults(monkeypatch):
    monkeypatch.setenv("METRICS_ENABLED", "true")
    monkeypatch.delenv("METRICS_TOKEN", raising=False)


@pytest.fixture
def client():
    with TestClient(create_app()) as c:
        yield c


class TestMetricsEndpoint:
    def test_returns_prometheus_text_format(self, client):
        res = client.get("/metrics")
        assert res.status_code == 200
        ctype = res.headers.get("content-type", "")
        # Prometheus exposition uses text/plain; the exact MIME string
        # carries a version param so just assert on the prefix.
        assert ctype.startswith("text/plain")
        body = res.text
        # The histogram must be defined in the registry on every boot
        # so dashboards do not need a "first request" warm-up.
        assert "voc_http_request_duration_seconds" in body
        assert "voc_webhook_delivery_total" in body
        assert "voc_ws_clients_total" in body
        assert "voc_ws_oids_active" in body
        assert "voc_active_sessions" in body
        assert "voc_webhook_dead_letter_size" in body
        assert "voc_rate_limit_blocks_total" in body
        assert "voc_rate_limit_blocked_buckets" in body

    def test_records_request_latency(self, client):
        # Hit a route a few times so the histogram has observations.
        for _ in range(3):
            client.get("/api/v1/auth/context")
        res = client.get("/metrics")
        # The route template (``/api/v1/auth/context``) must appear in
        # the metric output, not the raw path with any query string.
        body = res.text
        assert "/api/v1/auth/context" in body
        # And the count of observations for that bucket should be at
        # least the number of requests we just sent.
        # ``_count`` lines look like:
        #   voc_http_request_duration_seconds_count{...} 3.0
        count_lines = [
            ln
            for ln in body.splitlines()
            if ln.startswith("voc_http_request_duration_seconds_count") and "/api/v1/auth/context" in ln
        ]
        assert count_lines, "no observation recorded for /auth/context"
        # Parse the trailing float and require at least 3.
        for line in count_lines:
            try:
                value = float(line.rsplit(" ", 1)[1])
            except (IndexError, ValueError):
                continue
            assert value >= 3.0


class TestMetricsAccess:
    def test_metrics_is_unauthenticated(self, client):
        # Backwards-compatible default for service-mesh scraping.
        assert client.get("/metrics").status_code == 200

    def test_metrics_can_be_disabled(self, client, monkeypatch):
        monkeypatch.setenv("METRICS_ENABLED", "false")
        res = client.get("/metrics")
        assert res.status_code == 404

    def test_metrics_can_require_bearer_token(self, client, monkeypatch):
        monkeypatch.setenv("METRICS_TOKEN", "scrape-secret")
        missing = client.get("/metrics")
        assert missing.status_code == 401
        assert missing.headers["www-authenticate"] == 'Bearer realm="metrics"'
        assert (
            client.get(
                "/metrics",
                headers={"Authorization": "Bearer wrong"},
            ).status_code
            == 401
        )
        assert (
            client.get(
                "/metrics",
                headers={"Authorization": "Bearer scrape-secret"},
            ).status_code
            == 200
        )

    def test_metrics_token_is_not_accepted_from_query_string(
        self,
        client,
        monkeypatch,
    ):
        monkeypatch.setenv("METRICS_TOKEN", "scrape-secret")
        assert (
            client.get(
                "/metrics",
                params={"token": "scrape-secret"},
            ).status_code
            == 401
        )

    def test_disabled_wins_over_configured_token(self, client, monkeypatch):
        monkeypatch.setenv("METRICS_ENABLED", "false")
        monkeypatch.setenv("METRICS_TOKEN", "scrape-secret")
        assert (
            client.get(
                "/metrics",
                headers={"Authorization": "Bearer scrape-secret"},
            ).status_code
            == 404
        )


class TestOperationalGauges:
    def test_scrape_loads_persisted_dead_letter_depth(
        self,
        client,
        monkeypatch,
        tmp_path,
    ):
        from app.api import webhook_dead_letter

        monkeypatch.setattr(
            webhook_dead_letter,
            "_data_dir",
            lambda: str(tmp_path),
        )
        (tmp_path / "webhooks_dead_letter.jsonl").write_text(
            '{"event":"set_end"}\n{"event":"timeout"}\n',
            encoding="utf-8",
        )
        body = client.get("/metrics").text
        assert "voc_webhook_dead_letter_size 2.0" in body

    def test_scrape_reports_currently_blocked_rate_limit_buckets(
        self,
        client,
        monkeypatch,
    ):
        monkeypatch.setenv("AUTH_RATE_LIMIT_MAX_FAILURES", "1")
        assert client.get("/api/v1/state?oid=missing").status_code == 401
        assert client.get("/api/v1/state?oid=missing").status_code == 429
        body = client.get("/metrics").text
        assert 'voc_rate_limit_blocked_buckets{surface="api"} 1.0' in body


class TestWebhookCounter:
    """``record_webhook_outcome`` updates the labelled counter."""

    def test_success_outcome_increments_counter(self):
        from app.metrics import record_webhook_outcome, webhook_delivery_total

        # Snapshot the current value, increment, then assert delta.
        # ``_value.get()`` is the prometheus_client convention for
        # reading a Counter sample; tests in the python-prometheus
        # docs use the same pattern.
        sample = webhook_delivery_total.labels(event="set_end", status="success")
        before = sample._value.get()
        record_webhook_outcome("set_end", "success")
        assert sample._value.get() == before + 1


class TestWsGauges:
    """``WSHub`` keeps the two unlabelled gauges in sync."""

    def test_connect_disconnect_updates_gauges(self, monkeypatch):
        import asyncio as _asyncio
        from unittest.mock import AsyncMock

        from app.api.ws_hub import WSHub
        from app.metrics import ws_clients_total, ws_oids_active

        WSHub.clear()
        # Bypass the cap so we can register a synthetic socket.
        monkeypatch.setattr(WSHub, "_MAX_CLIENTS_PER_OID", 10)

        async def _go():
            ws = AsyncMock()
            await WSHub.connect(ws, "g-oid")
            return ws

        ws = _asyncio.run(_go())
        assert ws_clients_total._value.get() == 1
        assert ws_oids_active._value.get() == 1

        WSHub.disconnect(ws, "g-oid")
        assert ws_clients_total._value.get() == 0
        assert ws_oids_active._value.get() == 0
        WSHub.clear()
