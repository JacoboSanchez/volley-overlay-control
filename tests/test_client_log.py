"""Tests for ``POST /api/v1/_log`` (frontend error reporting endpoint)."""

import logging

import pytest
from fastapi.testclient import TestClient

from app.api.routes.client_log import _MAX_PER_WINDOW, _reset_rate_limiter
from app.bootstrap import create_app


@pytest.fixture(autouse=True)
def _reset_limiter():
    _reset_rate_limiter()
    yield
    _reset_rate_limiter()


@pytest.fixture
def client():
    return TestClient(create_app())


def test_returns_204_and_logs_at_error(client, caplog):
    payload = {
        "level": "error",
        "message": "Boom in render",
        "stack": "Error: Boom\n  at render",
        "href": "https://example/app#/match",
        "user_agent": "TestUA/1.0",
    }
    with caplog.at_level(logging.ERROR, logger="app.frontend"):
        response = client.post("/api/v1/_log", json=payload)
    assert response.status_code == 204
    matches = [r for r in caplog.records if r.name == "app.frontend"]
    assert matches, "expected a frontend log record"
    record = matches[0]
    assert record.levelno == logging.ERROR
    assert "Boom in render" in record.getMessage()
    assert "Error: Boom" in record.getMessage()


def test_warn_level_maps_to_warning(client, caplog):
    with caplog.at_level(logging.WARNING, logger="app.frontend"):
        response = client.post(
            "/api/v1/_log",
            json={"level": "warn", "message": "deprecated API call"},
        )
    assert response.status_code == 204
    matches = [r for r in caplog.records if r.name == "app.frontend"]
    assert matches and matches[0].levelno == logging.WARNING


def test_rejects_unknown_level(client):
    response = client.post(
        "/api/v1/_log",
        json={"level": "info", "message": "hi"},
    )
    assert response.status_code == 422


def test_rejects_empty_message(client):
    response = client.post(
        "/api/v1/_log",
        json={"level": "error", "message": ""},
    )
    assert response.status_code == 422


def test_oid_is_redacted_in_extras(client, caplog):
    with caplog.at_level(logging.ERROR, logger="app.frontend"):
        client.post(
            "/api/v1/_log",
            json={"level": "error", "message": "x", "oid": "secret-oid-1234"},
        )
    record = next(r for r in caplog.records if r.name == "app.frontend")
    assert record.frontend_oid == "secr***"


def test_href_query_string_is_redacted(client, caplog):
    with caplog.at_level(logging.ERROR, logger="app.frontend"):
        client.post(
            "/api/v1/_log",
            json={
                "level": "error",
                "message": "x",
                "href": "https://example.com/app?token=abc&oid=z",
            },
        )
    record = next(r for r in caplog.records if r.name == "app.frontend")
    assert "token" not in record.frontend_href
    assert record.frontend_href.startswith("https://example.com/app")


def test_rate_limited_after_window_exceeded(client, caplog):
    for _ in range(_MAX_PER_WINDOW):
        r = client.post("/api/v1/_log", json={"level": "error", "message": "x"})
        assert r.status_code == 204
    overflow = client.post("/api/v1/_log", json={"level": "error", "message": "x"})
    assert overflow.status_code == 429
