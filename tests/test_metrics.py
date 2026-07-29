"""Tests for the Prometheus exposition surface (M15)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.bootstrap import create_app

pytestmark = pytest.mark.usefixtures("clean_sessions")


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
            ln for ln in body.splitlines()
            if ln.startswith("voc_http_request_duration_seconds_count")
            and "/api/v1/auth/context" in ln
        ]
        assert count_lines, "no observation recorded for /auth/context"
        # Parse the trailing float and require at least 3.
        for line in count_lines:
            try:
                value = float(line.rsplit(" ", 1)[1])
            except (IndexError, ValueError):
                continue
            assert value >= 3.0


class TestMetricsOpenByDefault:
    def test_metrics_is_unauthenticated(self, client):
        # /metrics exposes only aggregates and stays open unless the
        # operator opts into a gate.
        assert client.get("/metrics").status_code == 200


class TestMetricsEnabledToggle:
    """``METRICS_ENABLED=false`` removes the endpoint."""

    def test_disabled_returns_404_not_403(self, client, monkeypatch):
        monkeypatch.setenv("METRICS_ENABLED", "false")
        res = client.get("/metrics")
        # 404, so a switched-off endpoint is indistinguishable from one
        # that was never mounted — 403 would advertise that it exists.
        assert res.status_code == 404
        assert "voc_http_request_duration_seconds" not in res.text

    def test_disabled_wins_over_a_valid_token(self, client, monkeypatch):
        monkeypatch.setenv("METRICS_ENABLED", "false")
        monkeypatch.setenv("METRICS_TOKEN", "scrape-secret")
        res = client.get(
            "/metrics", headers={"Authorization": "Bearer scrape-secret"},
        )
        assert res.status_code == 404

    @pytest.mark.parametrize("value", ["true", "1", "yes", "on"])
    def test_truthy_values_keep_it_mounted(self, client, monkeypatch, value):
        monkeypatch.setenv("METRICS_ENABLED", value)
        assert client.get("/metrics").status_code == 200

    def test_read_per_request_so_it_can_be_flipped(self, client, monkeypatch):
        assert client.get("/metrics").status_code == 200
        monkeypatch.setenv("METRICS_ENABLED", "false")
        assert client.get("/metrics").status_code == 404
        monkeypatch.setenv("METRICS_ENABLED", "true")
        assert client.get("/metrics").status_code == 200


class TestMetricsToken:
    """``METRICS_TOKEN`` turns the endpoint into a bearer-gated scrape."""

    @pytest.fixture(autouse=True)
    def _token(self, monkeypatch):
        monkeypatch.setenv("METRICS_TOKEN", "scrape-secret")

    def test_correct_bearer_token_is_accepted(self, client):
        res = client.get(
            "/metrics", headers={"Authorization": "Bearer scrape-secret"},
        )
        assert res.status_code == 200
        assert "voc_http_request_duration_seconds" in res.text

    def test_missing_credentials_are_challenged(self, client):
        res = client.get("/metrics")
        assert res.status_code == 401
        assert res.headers["www-authenticate"].startswith("Bearer")
        # The exposition must not leak past the gate.
        assert "voc_active_sessions" not in res.text

    @pytest.mark.parametrize(
        "header",
        [
            "Bearer wrong-secret",
            "Bearer ",
            "Basic scrape-secret",          # wrong scheme
            "scrape-secret",                # no scheme
            "Bearer scrape-secret-extra",   # prefix of the real token
            "Bearer scrape-secre",          # truncation of the real token
        ],
    )
    def test_bad_credentials_are_rejected(self, client, header):
        res = client.get("/metrics", headers={"Authorization": header})
        assert res.status_code == 401

    def test_scheme_matching_is_case_insensitive(self, client):
        # RFC 7235 auth schemes are case-insensitive; some scrapers send
        # a lowercase "bearer".
        res = client.get(
            "/metrics", headers={"Authorization": "bearer scrape-secret"},
        )
        assert res.status_code == 200

    def test_blank_token_is_treated_as_unset(self, client, monkeypatch):
        monkeypatch.setenv("METRICS_TOKEN", "   ")
        assert client.get("/metrics").status_code == 200

    def test_remote_config_blip_does_not_open_the_gate(self, client, monkeypatch):
        """A remotely-supplied token must survive a config-fetch failure.

        The cache used to drop to ``{}`` on a failed refresh, so the token
        reverted to "unset" and ``/metrics`` served the exposition with no
        auth until the config host recovered.
        """
        import time
        from unittest.mock import patch

        import requests

        from app.env_vars_manager import EnvVarsManager

        monkeypatch.delenv("METRICS_TOKEN", raising=False)
        monkeypatch.setenv("REMOTE_CONFIG_URL", "http://config.example/env.json")
        EnvVarsManager._remote_config_cache = {"METRICS_TOKEN": "remote-secret"}
        EnvVarsManager._cache_timestamp = time.time()
        EnvVarsManager._refresh_in_flight = False
        try:
            assert client.get("/metrics").status_code == 401
            with patch(
                "app.env_vars_manager.requests.get",
                side_effect=requests.exceptions.ConnectionError("blip"),
            ):
                EnvVarsManager._refresh("http://config.example/env.json")
                assert client.get("/metrics").status_code == 401
                assert client.get(
                    "/metrics", headers={"Authorization": "Bearer remote-secret"},
                ).status_code == 200
        finally:
            EnvVarsManager._remote_config_cache = {}
            EnvVarsManager._cache_timestamp = 0
            EnvVarsManager._refresh_in_flight = False

    def test_non_ascii_token_rejects_rather_than_500s(self, client, monkeypatch):
        # hmac.compare_digest raises TypeError on non-ASCII str arguments,
        # so a misconfigured operator could turn every scrape into a 500.
        # Comparing as bytes makes it a plain 401. (The matching-token case
        # is unreachable over HTTP — headers cannot carry these bytes — so
        # such a token simply never authenticates anyone.)
        monkeypatch.setenv("METRICS_TOKEN", "sécret-ünicode")
        assert client.get(
            "/metrics", headers={"Authorization": "Bearer wrong"},
        ).status_code == 401


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
