"""Tests for :mod:`app.logging_context` and the request middleware."""

import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.middleware.logging import MAX_REQUEST_ID_LEN, RequestContextMiddleware
from app.logging_context import (
    ContextFilter,
    new_request_id,
    oid_var,
    request_id_var,
    trace_id_var,
)


def _build_app():
    app = FastAPI()

    @app.get("/probe")
    async def probe():
        return {
            "request_id": request_id_var.get(),
            "oid": oid_var.get(),
            "trace_id": trace_id_var.get(),
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
        assert trace_id_var.get() == "-"


class TestRequestIdIsBounded:
    """A caller cannot choose unbounded log/header content.

    The id is echoed in a response header *and* interpolated into every
    log line for the request, so an unvalidated one is a log-inflation
    primitive. Rejected ids fall back to a generated uuid4 hex.
    """

    @staticmethod
    def _is_generated(rid: str) -> bool:
        return len(rid) == 32 and all(c in "0123456789abcdef" for c in rid)

    def test_oversized_id_is_replaced_not_echoed(self):
        client = TestClient(_build_app())
        huge = "a" * 4096
        response = client.get("/probe", headers={"x-request-id": huge})
        rid = response.json()["request_id"]
        assert huge not in rid
        assert self._is_generated(rid)
        assert response.headers["x-request-id"] == rid

    def test_id_at_the_limit_is_still_honoured(self):
        client = TestClient(_build_app())
        at_limit = "a" * MAX_REQUEST_ID_LEN
        response = client.get("/probe", headers={"x-request-id": at_limit})
        assert response.json()["request_id"] == at_limit

    def test_one_over_the_limit_is_rejected(self):
        client = TestClient(_build_app())
        over = "a" * (MAX_REQUEST_ID_LEN + 1)
        assert self._is_generated(
            client.get("/probe", headers={"x-request-id": over}).json()["request_id"],
        )

    @pytest.mark.parametrize(
        "value",
        [
            "has space",
            "semi;colon",
            "angle<bracket>",
            "quote\"d",
            "percent%0d%0a",   # only decoded downstream, but never ours to echo
            "-",               # the sentinel used for "no request id"
        ],
    )
    def test_disallowed_characters_are_rejected(self, value):
        client = TestClient(_build_app())
        rid = client.get("/probe", headers={"x-request-id": value}).json()["request_id"]
        assert rid != value
        assert self._is_generated(rid)


    @pytest.mark.parametrize(
        "value",
        [
            "caller-rid-123",
            "0af7651916cd43dd8448eb211c80319c",
            "6d7f0e6c-6b1a-4f2e-9c1a-3a2b1c0d9e8f",
            "svc.edge_01-42",
        ],
    )
    def test_conventional_ids_are_preserved(self, value):
        client = TestClient(_build_app())
        response = client.get("/probe", headers={"x-request-id": value})
        assert response.json()["request_id"] == value
        assert response.headers["x-request-id"] == value

    def test_surrounding_whitespace_is_stripped(self):
        client = TestClient(_build_app())
        response = client.get("/probe", headers={"x-request-id": "  padded-id  "})
        assert response.json()["request_id"] == "padded-id"

    def test_blank_id_falls_back_to_generated(self):
        client = TestClient(_build_app())
        rid = client.get("/probe", headers={"x-request-id": "   "}).json()["request_id"]
        assert self._is_generated(rid)


class TestRequestIdSanitizerAtTheAsgiBoundary:
    """Byte-level cases an HTTP client refuses to send but ASGI can carry.

    ``httpx`` rejects a non-ASCII or CR/LF header value before it reaches
    the server, so these are unreachable through ``TestClient`` — but a
    raw ASGI scope (another middleware, a non-HTTP transport, a
    hand-rolled server) is not bound by that.
    """

    @staticmethod
    def _extract(value: bytes):
        from app.api.middleware.logging import _extract_request_id

        return _extract_request_id({"headers": [(b"x-request-id", value)]})

    @pytest.mark.parametrize(
        "value",
        [
            b"\xff\xfe binary",
            b"caf\xe9",                  # latin-1 non-ASCII
            b"split\r\nX-Injected: 1",   # header-splitting attempt
            b"nul\x00byte",
            b"\x1b[31mansi",             # ANSI escape aimed at a terminal log
            b"a" * 4096,
        ],
    )
    def test_hostile_bytes_are_rejected(self, value):
        assert self._extract(value) is None

    def test_plain_ascii_id_survives(self):
        assert self._extract(b"edge-01-abc") == "edge-01-abc"

    def test_missing_header_returns_none(self):
        from app.api.middleware.logging import _extract_request_id

        assert _extract_request_id({"headers": []}) is None
        assert _extract_request_id({}) is None


class TestTraceContextPropagation:
    """A valid inbound W3C ``traceparent`` is adopted for correlation."""

    VALID = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
    TRACE_ID = "0af7651916cd43dd8448eb211c80319c"

    def test_trace_id_is_captured(self):
        client = TestClient(_build_app())
        body = client.get("/probe", headers={"traceparent": self.VALID}).json()
        assert body["trace_id"] == self.TRACE_ID

    def test_trace_id_becomes_the_request_id_when_none_was_sent(self):
        # Without this, our logs invent a second correlation id for a
        # request the upstream is already tracing.
        client = TestClient(_build_app())
        response = client.get("/probe", headers={"traceparent": self.VALID})
        assert response.json()["request_id"] == self.TRACE_ID
        assert response.headers["x-request-id"] == self.TRACE_ID

    def test_explicit_request_id_wins_over_traceparent(self):
        client = TestClient(_build_app())
        body = client.get(
            "/probe",
            headers={"traceparent": self.VALID, "x-request-id": "caller-chosen"},
        ).json()
        assert body["request_id"] == "caller-chosen"
        # The trace is still recorded — the two are complementary.
        assert body["trace_id"] == self.TRACE_ID

    def test_absent_traceparent_leaves_the_sentinel(self):
        client = TestClient(_build_app())
        assert client.get("/probe").json()["trace_id"] == "-"

    @pytest.mark.parametrize(
        "value",
        [
            "",
            "garbage",
            "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331",  # too few fields
            "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01-extra",  # v00 is 4
            "ff-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01",  # reserved ver
            "00-" + "0" * 32 + "-b7ad6b7169203331-01",   # all-zero trace-id
            "00-0af7651916cd43dd8448eb211c80319c-" + "0" * 16 + "-01",  # zero parent
            "00-0AF7651916CD43DD8448EB211C80319C-b7ad6b7169203331-01",  # uppercase
            "00-0af7651916cd43dd8448eb211c8031-b7ad6b7169203331-01",  # short trace-id
        ],
    )
    def test_malformed_traceparent_is_ignored(self, value):
        client = TestClient(_build_app())
        body = client.get("/probe", headers={"traceparent": value}).json()
        assert body["trace_id"] == "-"
        # And it must never leak into the request id either.
        assert len(body["request_id"]) == 32
        assert body["request_id"] not in value

    def test_future_version_may_carry_extra_fields(self):
        # W3C requires forward compatibility: a later version can append
        # fields, and a parser must still read the first four.
        client = TestClient(_build_app())
        header = f"01-{self.TRACE_ID}-b7ad6b7169203331-01-extra-stuff"
        assert client.get(
            "/probe", headers={"traceparent": header},
        ).json()["trace_id"] == self.TRACE_ID


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

    def test_trace_id_is_attached_only_when_present(self):
        record = logging.LogRecord(
            name="t", level=logging.INFO, pathname="", lineno=0,
            msg="m", args=None, exc_info=None,
        )
        ContextFilter().filter(record)
        # Absent, not "-": deployments with no upstream tracing keep the
        # exact log shape they had before trace context existed.
        assert not hasattr(record, "trace_id")

        token = trace_id_var.set("0af7651916cd43dd8448eb211c80319c")
        try:
            record = logging.LogRecord(
                name="t", level=logging.INFO, pathname="", lineno=0,
                msg="m", args=None, exc_info=None,
            )
            ContextFilter().filter(record)
            assert record.trace_id == "0af7651916cd43dd8448eb211c80319c"
        finally:
            trace_id_var.reset(token)

    def test_trace_id_reaches_the_json_log_line(self):
        import json

        from app.logging_config import JsonFormatter

        token = trace_id_var.set("0af7651916cd43dd8448eb211c80319c")
        try:
            record = logging.LogRecord(
                name="t", level=logging.INFO, pathname="", lineno=0,
                msg="m", args=None, exc_info=None,
            )
            ContextFilter().filter(record)
            payload = json.loads(JsonFormatter().format(record))
        finally:
            trace_id_var.reset(token)
        assert payload["trace_id"] == "0af7651916cd43dd8448eb211c80319c"


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
