"""Tests for :mod:`app.logging_context` and the request middleware."""

import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.middleware.logging import RequestContextMiddleware
from app.logging_context import (
    ContextFilter,
    new_request_id,
    oid_var,
    request_id_var,
)


def _build_app():
    app = FastAPI()

    @app.get("/probe")
    async def probe():
        return {
            "request_id": request_id_var.get(),
            "oid": oid_var.get(),
        }

    app.add_middleware(RequestContextMiddleware)
    return app


class TestRequestContextMiddleware:
    def test_generates_request_id_when_absent(self):
        client = TestClient(_build_app())
        response = client.get("/probe")
        assert response.status_code == 200
        rid = response.json()["request_id"]
        assert rid != "-"
        assert len(rid) == 32  # uuid4 hex
        assert response.headers["x-request-id"] == rid

    def test_honors_incoming_header(self):
        client = TestClient(_build_app())
        response = client.get(
            "/probe", headers={"x-request-id": "caller-rid-123"},
        )
        assert response.json()["request_id"] == "caller-rid-123"
        assert response.headers["x-request-id"] == "caller-rid-123"

    def test_extracts_oid_from_query_string(self):
        client = TestClient(_build_app())
        response = client.get("/probe", params={"oid": "test_oid_valid"})
        assert response.json()["oid"] == "test_oid_valid"

    def test_extracts_oid_from_control_alias(self):
        client = TestClient(_build_app())
        response = client.get("/probe", params={"control": "test_oid_valid"})
        assert response.json()["oid"] == "test_oid_valid"

    def test_absent_oid_defaults_to_dash(self):
        client = TestClient(_build_app())
        response = client.get("/probe")
        assert response.json()["oid"] == "-"

    def test_context_is_isolated_between_requests(self):
        client = TestClient(_build_app())
        r1 = client.get("/probe", headers={"x-request-id": "first"})
        r2 = client.get("/probe", headers={"x-request-id": "second"})
        assert r1.json()["request_id"] == "first"
        assert r2.json()["request_id"] == "second"
        assert request_id_var.get() == "-"
        assert oid_var.get() == "-"


class TestContextFilter:
    def test_fills_missing_fields_from_contextvars(self):
        rid_token = request_id_var.set("abc")
        oid_token = oid_var.set("abcdef123")
        try:
            record = logging.LogRecord(
                name="t", level=logging.INFO, pathname="", lineno=0,
                msg="m", args=None, exc_info=None,
            )
            assert ContextFilter().filter(record) is True
            assert record.request_id == "abc"
            # ContextFilter redacts the oid so it cannot leak verbatim.
            assert record.oid == "abcd***"
        finally:
            request_id_var.reset(rid_token)
            oid_var.reset(oid_token)

    def test_preserves_explicit_extra_values(self):
        record = logging.LogRecord(
            name="t", level=logging.INFO, pathname="", lineno=0,
            msg="m", args=None, exc_info=None,
        )
        record.request_id = "from-extra"
        record.oid = "also-from-extra"
        ContextFilter().filter(record)
        assert record.request_id == "from-extra"
        assert record.oid == "also-from-extra"


def test_new_request_id_is_unique():
    ids = {new_request_id() for _ in range(100)}
    assert len(ids) == 100


def test_caplog_helper_reports_actual_captured(caplog):
    from tests.helpers.logging import assert_logged

    logger = logging.getLogger("t.helper")
    with caplog.at_level(logging.INFO, logger="t.helper"):
        logger.info("hello world")

    record = assert_logged(caplog, logging.INFO, "hello")
    assert record.getMessage() == "hello world"

    with pytest.raises(AssertionError) as exc:
        assert_logged(caplog, logging.ERROR, "missing")
    assert "missing" in str(exc.value)
