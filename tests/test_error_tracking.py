"""Tests for the opt-in Sentry integration boundary."""

from __future__ import annotations

from app import error_tracking


def test_no_dsn_is_a_noop(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    called = False

    def fake_init(**_options):
        nonlocal called
        called = True

    monkeypatch.setattr(error_tracking, "_init_sentry", fake_init)
    assert error_tracking.configure_error_tracking() is False
    assert called is False


def test_dsn_enables_privacy_safe_sentry_options(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://public@example.invalid/1")
    monkeypatch.setenv("SENTRY_ENVIRONMENT", "production")
    monkeypatch.setenv("SENTRY_RELEASE", "7.0.0")
    monkeypatch.setenv("SENTRY_TRACES_SAMPLE_RATE", "0.25")
    captured = {}

    def fake_init(**options):
        captured.update(options)

    monkeypatch.setattr(error_tracking, "_init_sentry", fake_init)
    assert error_tracking.configure_error_tracking() is True
    assert captured["dsn"] == "https://public@example.invalid/1"
    assert captured["environment"] == "production"
    assert captured["release"] == "7.0.0"
    assert captured["traces_sample_rate"] == 0.25
    assert captured["send_default_pii"] is False
    assert captured["max_request_body_size"] == "never"
    assert captured["include_local_variables"] is False
    # Sampled transactions never reach ``before_send``; they need their own hook.
    assert captured["before_send"] is error_tracking._before_send
    assert (
        captured["before_send_transaction"]
        is error_tracking._before_send_transaction
    )


def test_before_send_removes_credentials_body_and_capability_url():
    event = {
        "request": {
            "url": "https://user:pass@example.test/overlay/secret?sig=hidden",
            "query_string": "sig=hidden",
            "cookies": {"vsession": "secret"},
            "data": {"password": "secret"},
            "headers": {
                "Authorization": "Bearer secret",
                "Cookie": "vsession=secret",
                "Content-Type": "application/json",
                "traceparent": "00-trace",
                "X-Request-ID": "safe-id",
                "User-Agent": "x" * 300,
            },
        },
    }
    result = error_tracking._before_send(event, {})
    request = result["request"]
    assert request["url"] == "https://example.test/overlay/***"
    assert request["query_string"] == ""
    assert "cookies" not in request
    assert "data" not in request
    assert "Authorization" not in request["headers"]
    assert "Cookie" not in request["headers"]
    assert "traceparent" not in request["headers"]
    assert "User-Agent" not in request["headers"]
    assert request["headers"]["Content-Type"] == "application/json"
    assert request["headers"]["X-Request-ID"] == "safe-id"


def test_before_send_redacts_every_capability_path_prefix():
    for prefix in ("/overlay/", "/follow/", "/ws/", "/matches/", "/match/"):
        event = {"request": {"url": f"https://example.test{prefix}tok3n/report"}}
        result = error_tracking._before_send(event, {})
        assert result["request"]["url"] == f"https://example.test{prefix}***"


def test_before_send_scrubs_breadcrumb_urls_and_queries():
    event = {
        "breadcrumbs": {
            "values": [
                {
                    "category": "httplib",
                    "data": {
                        "url": "https://hook.test/match/abc/report?sig=secret",
                        "http.query": "sig=secret",
                        "method": "POST",
                    },
                },
            ],
        },
    }
    data = error_tracking._before_send(event, {})["breadcrumbs"]["values"][0]["data"]
    assert data["url"] == "https://hook.test/match/***"
    assert "http.query" not in data
    assert data["method"] == "POST"


def test_before_send_transaction_scrubs_request_spans_and_name():
    event = {
        "type": "transaction",
        "transaction": "/matches/tok3n",
        "request": {
            "url": "https://example.test/matches/tok3n?sig=hidden",
            "query_string": "sig=hidden",
            "cookies": {"vsession": "secret"},
            "headers": {"Cookie": "vsession=secret"},
        },
        "contexts": {
            "trace": {
                "op": "http.server",
                "description": "GET /matches/tok3n?sig=hidden",
                "data": {"url.query": "sig=hidden"},
            },
        },
        "spans": [
            {
                "op": "http.client",
                "description": "POST https://hook.test/follow/tok3n?sig=hidden",
                "data": {
                    "http.url": "https://hook.test/follow/tok3n?sig=hidden",
                    "url.query": "sig=hidden",
                    "http.response.status_code": 200,
                },
            },
            "not-a-span",
        ],
    }

    result = error_tracking._before_send_transaction(event, {})

    assert result["transaction"] == "/matches/***"
    request = result["request"]
    assert request["url"] == "https://example.test/matches/***"
    assert request["query_string"] == ""
    assert "cookies" not in request
    assert request["headers"] == {}
    trace = result["contexts"]["trace"]
    assert trace["description"] == "GET /matches/***"
    assert "url.query" not in trace["data"]
    span = result["spans"][0]
    assert span["description"] == "POST https://hook.test/follow/***"
    assert span["data"]["http.url"] == "https://hook.test/follow/***"
    assert "url.query" not in span["data"]
    assert span["data"]["http.response.status_code"] == 200


def test_before_send_transaction_leaves_non_url_payloads_alone():
    event = {
        "type": "transaction",
        "transaction": "app.api.routes.matches.get_match",
        "spans": [{"op": "db", "description": "SELECT 1 FROM matches"}],
    }

    result = error_tracking._before_send_transaction(event, {})

    assert result["transaction"] == "app.api.routes.matches.get_match"
    assert result["spans"][0]["description"] == "SELECT 1 FROM matches"


def test_bad_sample_rate_disables_tracing_without_blocking_errors(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://public@example.invalid/1")
    monkeypatch.setenv("SENTRY_TRACES_SAMPLE_RATE", "not-a-number")
    captured = {}
    monkeypatch.setattr(
        error_tracking,
        "_init_sentry",
        lambda **options: captured.update(options),
    )
    assert error_tracking.configure_error_tracking() is True
    assert captured["traces_sample_rate"] == 0.0


def test_initialization_failure_does_not_block_startup(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://public@example.invalid/1")

    def fail_init(**_options):
        raise RuntimeError("unavailable")

    monkeypatch.setattr(error_tracking, "_init_sentry", fail_init)
    assert error_tracking.configure_error_tracking() is False
