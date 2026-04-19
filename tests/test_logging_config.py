"""Tests for :mod:`app.logging_config`."""

import json
import logging

import pytest

from app.logging_config import (
    HealthEndpointFilter,
    JsonFormatter,
    RedactFilter,
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

    def test_timestamp_carries_millisecond_precision(self):
        record = _make_record()
        payload = json.loads(JsonFormatter().format(record))
        assert "." in payload["timestamp"]
        seconds, _, ms = payload["timestamp"].rpartition(".")
        assert seconds.count(":") == 2  # HH:MM:SS
        assert len(ms) == 3 and ms.isdigit()

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

    def test_handlers_have_redact_filter(self):
        cfg = build_dict_config()
        assert "redact" in cfg["handlers"]["default"]["filters"]
        assert "redact" in cfg["handlers"]["access"]["filters"]

    def test_file_handler_omitted_by_default(self, monkeypatch):
        monkeypatch.delenv("LOG_FILE", raising=False)
        cfg = build_dict_config()
        assert "file" not in cfg["handlers"]
        assert cfg["root"]["handlers"] == ["default"]

    def test_file_handler_attached_when_log_file_set(self, tmp_path):
        target = tmp_path / "app.log"
        cfg = build_dict_config(log_file=str(target))
        file_h = cfg["handlers"]["file"]
        assert file_h["class"] == "logging.handlers.RotatingFileHandler"
        assert file_h["filename"] == str(target)
        assert file_h["formatter"] == "json"
        assert "redact" in file_h["filters"]
        assert "file" in cfg["root"]["handlers"]
        assert "file" in cfg["loggers"]["uvicorn.access"]["handlers"]

    def test_file_handler_honors_rotation_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LOG_FILE_MAX_BYTES", "2048")
        monkeypatch.setenv("LOG_FILE_BACKUPS", "3")
        cfg = build_dict_config(log_file=str(tmp_path / "x.log"))
        assert cfg["handlers"]["file"]["maxBytes"] == 2048
        assert cfg["handlers"]["file"]["backupCount"] == 3

    def test_file_handler_falls_back_on_invalid_int(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LOG_FILE_MAX_BYTES", "not-a-number")
        monkeypatch.setenv("LOG_FILE_BACKUPS", "-1")
        cfg = build_dict_config(log_file=str(tmp_path / "x.log"))
        assert cfg["handlers"]["file"]["maxBytes"] == 10 * 1024 * 1024
        assert cfg["handlers"]["file"]["backupCount"] == 5

    def test_file_handler_accepts_zero_for_no_rotation(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LOG_FILE_MAX_BYTES", "0")
        monkeypatch.setenv("LOG_FILE_BACKUPS", "0")
        cfg = build_dict_config(log_file=str(tmp_path / "x.log"))
        assert cfg["handlers"]["file"]["maxBytes"] == 0
        assert cfg["handlers"]["file"]["backupCount"] == 0


class TestRedactFilter:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("Authorization: Bearer abc.def-123", "Authorization: Bearer ***"),
            ("token=abc123 next", "token=*** next"),
            ("password=p@ss&keep=this", "password=***&keep=this"),
            ("api_key=KEY123 done", "api_key=*** done"),
            ("api-key=KEY123 done", "api-key=*** done"),
            ("secret=s3cr3t end", "secret=*** end"),
            ("nothing to redact here", "nothing to redact here"),
        ],
    )
    def test_scrubs_known_secret_patterns(self, raw, expected):
        record = _make_record(msg=raw)
        RedactFilter().filter(record)
        assert record.getMessage() == expected

    def test_clears_args_after_substitution(self):
        record = _make_record(msg="token=%s", args=("abc",))
        RedactFilter().filter(record)
        # After scrubbing the rendered message, args must not be re-applied.
        assert record.args is None
        assert record.getMessage() == "token=***"

    def test_leaves_unrelated_args_alone(self):
        record = _make_record(msg="hello %s", args=("world",))
        RedactFilter().filter(record)
        assert record.args == ("world",)
        assert record.getMessage() == "hello world"


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
