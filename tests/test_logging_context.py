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
from app.trace_context import trace_id_var, traceparent_var, tracestate_var

_UPSTREAM_TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"
_UPSTREAM_PARENT_ID = "00f067aa0ba902b7"
_UPSTREAM_TRACEPARENT = f"00-{_UPSTREAM_TRACE_ID}-{_UPSTREAM_PARENT_ID}-01"


def _build_app():
    app = FastAPI()

    @app.get("/probe")
    async def probe():
        return {
            "request_id": request_id_var.get(),
            "oid": oid_var.get(),
            "trace_id": trace_id_var.get(),
            "traceparent": traceparent_var.get(),
            "tracestate": tracestate_var.get(),
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
            "/probe",
            headers={"x-request-id": "caller-rid-123"},
        )
        assert response.json()["request_id"] == "caller-rid-123"
        assert response.headers["x-request-id"] == "caller-rid-123"

    @pytest.mark.parametrize(
        "request_id",
        [
            "x" * 65,
            "has spaces",
            "slash/not-allowed",
            "semi;colon",
        ],
    )
    def test_rejects_unbounded_or_unsafe_request_id(self, request_id):
        client = TestClient(_build_app())
        response = client.get("/probe", headers={"x-request-id": request_id})
        generated = response.json()["request_id"]
        assert len(generated) == 32
        assert generated != request_id
        assert response.headers["x-request-id"] == generated

    def test_continues_valid_w3c_trace_and_correlates_default_request_id(self):
        client = TestClient(_build_app())
        response = client.get(
            "/probe",
            headers={
                "traceparent": _UPSTREAM_TRACEPARENT,
                "tracestate": "vendor=value",
            },
        )
        payload = response.json()
        assert payload["trace_id"] == _UPSTREAM_TRACE_ID
        assert payload["request_id"] == _UPSTREAM_TRACE_ID
        assert payload["tracestate"] == "vendor=value"
        child = payload["traceparent"]
        assert child.startswith(f"00-{_UPSTREAM_TRACE_ID}-")
        assert child.endswith("-01")
        assert child != _UPSTREAM_TRACEPARENT
        assert response.headers["traceparent"] == child

    def test_invalid_traceparent_restarts_trace_and_discards_tracestate(self):
        client = TestClient(_build_app())
        response = client.get(
            "/probe",
            headers={
                "traceparent": "00-" + ("0" * 32) + "-" + ("0" * 16) + "-01",
                "tracestate": "vendor=must-not-propagate",
            },
        )
        payload = response.json()
        assert payload["trace_id"] != "0" * 32
        assert len(payload["trace_id"]) == 32
        assert payload["tracestate"] == "-"

    @pytest.mark.parametrize(
        "tracestate",
        [
            "UPPER=value",
            "vendor=value=extra",
            "vendor=value,vendor=duplicate",
            ",".join(f"vendor{i}=value" for i in range(33)),
            "vendor=" + ("x" * 500),
        ],
    )
    def test_invalid_or_unbounded_tracestate_is_not_propagated(self, tracestate):
        client = TestClient(_build_app())
        response = client.get(
            "/probe",
            headers={
                "traceparent": _UPSTREAM_TRACEPARENT,
                "tracestate": tracestate,
            },
        )
        assert response.json()["trace_id"] == _UPSTREAM_TRACE_ID
        assert response.json()["tracestate"] == "-"

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
        assert trace_id_var.get() == "-"
        assert traceparent_var.get() == "-"
        assert tracestate_var.get() == "-"


class TestContextFilter:
    def test_fills_missing_fields_from_contextvars(self):
        rid_token = request_id_var.set("abc")
        oid_token = oid_var.set("abcdef123")
        try:
            record = logging.LogRecord(
                name="t",
                level=logging.INFO,
                pathname="",
                lineno=0,
                msg="m",
                args=None,
                exc_info=None,
            )
            assert ContextFilter().filter(record) is True
            assert record.request_id == "abc"
            assert record.trace_id == "-"
            # ContextFilter redacts the oid so it cannot leak verbatim.
            assert record.oid == "abcd***"
        finally:
            request_id_var.reset(rid_token)
            oid_var.reset(oid_token)

    def test_preserves_explicit_extra_values(self):
        record = logging.LogRecord(
            name="t",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="m",
            args=None,
            exc_info=None,
        )
        record.request_id = "from-extra"
        record.oid = "also-from-extra"
        ContextFilter().filter(record)
        assert record.request_id == "from-extra"
        assert record.oid == "also-from-extra"
        assert record.trace_id == "-"


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
