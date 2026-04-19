"""Tests for :mod:`app.logging_config`."""

import json
import logging

import pytest

from app.logging_config import (
    HealthEndpointFilter,
    JsonFormatter,
    TextFormatter,
    build_dict_config,
)
from app.logging_context import oid_var, request_id_var


def _make_record(
    level=logging.INFO, msg="hello", name="app.test", args=None,
):
    return logging.LogRecord(
        name=name, level=level, pathname=__file__, lineno=1,
        msg=msg, args=args, exc_info=None,
    )


class TestTextFormatter:
    def test_omits_context_when_empty(self):
        record = _make_record()
        out = TextFormatter().format(record)
        assert "rid=" not in out
        assert "hello" in out
        assert record.name in out

    def test_includes_context_when_present(self):
        record = _make_record()
        record.request_id = "req-1"
        record.oid = "abcd***"
        out = TextFormatter().format(record)
        assert "rid=req-1" in out
        assert "oid=abcd***" in out


class TestJsonFormatter:
    def test_emits_valid_json(self):
        record = _make_record(msg="event %s", args=("x",))
        payload = json.loads(JsonFormatter().format(record))
        assert payload["message"] == "event x"
        assert payload["level"] == "INFO"
        assert payload["logger"] == "app.test"
        assert "timestamp" in payload

    def test_defaults_context_fields_to_dash(self):
        record = _make_record()
        payload = json.loads(JsonFormatter().format(record))
        assert payload["request_id"] == "-"
        assert payload["oid"] == "-"

    def test_includes_context_fields_from_record(self):
        record = _make_record()
        record.request_id = "req-7"
        record.oid = "zzzz"
        payload = json.loads(JsonFormatter().format(record))
        assert payload["request_id"] == "req-7"
        assert payload["oid"] == "zzzz"

    def test_serializes_exc_info(self):
        try:
            raise ValueError("boom")
        except ValueError:
            import sys
            record = logging.LogRecord(
                name="t", level=logging.ERROR, pathname="", lineno=0,
                msg="oops", args=None, exc_info=sys.exc_info(),
            )
        payload = json.loads(JsonFormatter().format(record))
        assert "ValueError: boom" in payload["exc_info"]


class TestHealthEndpointFilter:
    @pytest.mark.parametrize("path", ["/health", "/manifest.webmanifest", "/favicon.ico"])
    def test_drops_noisy_paths(self, path):
        record = _make_record(args=("1.2.3.4", "GET", path, "1.1", 200))
        assert HealthEndpointFilter().filter(record) is False

    def test_keeps_real_endpoints(self):
        record = _make_record(
            args=("1.2.3.4", "POST", "/api/v1/session/init", "1.1", 200),
        )
        assert HealthEndpointFilter().filter(record) is True

    def test_passes_records_with_non_access_args(self):
        record = _make_record()  # no args
        assert HealthEndpointFilter().filter(record) is True


class TestBuildDictConfig:
    def test_defaults_to_text(self, monkeypatch):
        monkeypatch.delenv("LOG_FORMAT", raising=False)
        monkeypatch.delenv("LOGGING_LEVEL", raising=False)
        cfg = build_dict_config()
        assert cfg["handlers"]["default"]["formatter"] == "text"
        assert cfg["root"]["level"] == "WARNING"

    def test_json_mode(self, monkeypatch):
        monkeypatch.setenv("LOG_FORMAT", "json")
        cfg = build_dict_config()
        assert cfg["handlers"]["default"]["formatter"] == "json"

    def test_invalid_level_falls_back(self, monkeypatch):
        monkeypatch.setenv("LOGGING_LEVEL", "LOUD")
        cfg = build_dict_config()
        assert cfg["root"]["level"] == "WARNING"

    def test_explicit_override_wins(self, monkeypatch):
        monkeypatch.setenv("LOGGING_LEVEL", "warning")
        cfg = build_dict_config(level="DEBUG", fmt="json")
        assert cfg["root"]["level"] == "DEBUG"
        assert cfg["handlers"]["default"]["formatter"] == "json"

    def test_uvicorn_access_has_health_filter(self):
        cfg = build_dict_config()
        assert "health" in cfg["handlers"]["access"]["filters"]


def test_context_filter_uses_contextvar_values():
    from app.logging_context import ContextFilter

    rid_token = request_id_var.set("ctx-rid")
    oid_token = oid_var.set("abcdef")
    try:
        record = _make_record()
        ContextFilter().filter(record)
        assert record.request_id == "ctx-rid"
        # oid is redacted at the logging boundary (first 4 + ***).
        assert record.oid == "abcd***"
    finally:
        request_id_var.reset(rid_token)
        oid_var.reset(oid_token)


def test_context_filter_passes_dash_through_unredacted():
    """The default "-" sentinel must not be masked to ``***``."""
    from app.logging_context import ContextFilter

    record = _make_record()
    ContextFilter().filter(record)
    assert record.request_id == "-"
    assert record.oid == "-"
