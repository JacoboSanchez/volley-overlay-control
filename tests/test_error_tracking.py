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
