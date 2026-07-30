"""Tests for the redaction helpers in :mod:`app.logging_utils`.

The capability-path maskers are the load-bearing ones: a raw
``/overlay/<public_token>`` in a log line or an error report is a live
credential, not merely PII.
"""
from __future__ import annotations

import pytest

from app.logging_utils import (
    _reset_cache_for_tests,
    mask_capability_tokens,
    redact_path,
)


@pytest.fixture(autouse=True)
def _reset_redact_cache():
    _reset_cache_for_tests()
    yield
    _reset_cache_for_tests()


class TestMaskCapabilityTokens:
    @pytest.mark.parametrize(
        "path,expected",
        [
            ("/overlay/tok_abc", "/overlay/***"),
            ("/follow/tok_abc", "/follow/***"),
            ("/ws/tok_abc", "/ws/***"),
            ("/matches/tok_abc", "/matches/***"),
            ("/match/mid_abc/report", "/match/***/report"),
        ],
    )
    def test_each_capability_surface_is_masked(self, path, expected):
        assert mask_capability_tokens(path) == expected

    def test_masks_an_occurrence_embedded_in_a_message(self):
        # This is the shape ExceptionLoggingMiddleware produces.
        msg = "Unhandled http on GET /overlay/tok_abc — RuntimeError (request_id=r1)"
        out = mask_capability_tokens(msg)
        assert "tok_abc" not in out
        assert "/overlay/***" in out
        # The rest of the message survives for triage.
        assert "RuntimeError" in out and "request_id=r1" in out

    @pytest.mark.parametrize(
        "path",
        [
            # An authenticated API route that merely *contains* a watched
            # word. Masking the resource id here would cost triage value
            # without protecting a capability.
            "/api/v1/matches/mid_abc",
            "/api/v1/matches",
            "/api/v1/game/add-point",
            "/health",
            "/",
        ],
    )
    def test_unrelated_paths_are_left_readable(self, path):
        assert mask_capability_tokens(path) == path

    def test_prefix_without_a_token_is_untouched(self):
        assert mask_capability_tokens("/overlay/") == "/overlay/"
        assert mask_capability_tokens("/overlay") == "/overlay"

    def test_stops_at_a_query_or_fragment(self):
        assert mask_capability_tokens("/overlay/tok_abc?lang=es") == (
            "/overlay/***?lang=es"
        )
        assert mask_capability_tokens("/overlay/tok_abc#x") == "/overlay/***#x"

    def test_masks_every_occurrence(self):
        out = mask_capability_tokens("/overlay/a then /follow/b")
        assert out == "/overlay/*** then /follow/***"

    def test_empty_input_passes_through(self):
        assert mask_capability_tokens("") == ""

    def test_is_not_disabled_by_log_redact(self, monkeypatch):
        # Unconditional on purpose: callers include the error-reporter
        # path, where the value leaves the process entirely. A dev-only
        # "show raw values" switch must not become an exfiltration channel.
        monkeypatch.setenv("LOG_REDACT", "0")
        _reset_cache_for_tests()
        assert mask_capability_tokens("/overlay/tok_abc") == "/overlay/***"


class TestRedactPath:
    def test_masks_by_default(self):
        assert redact_path("/overlay/tok_abc") == "/overlay/***"

    def test_honours_log_redact_opt_out(self, monkeypatch):
        # Our own sinks may legitimately show raw values in local dev.
        monkeypatch.setenv("LOG_REDACT", "0")
        _reset_cache_for_tests()
        assert redact_path("/overlay/tok_abc") == "/overlay/tok_abc"

    @pytest.mark.parametrize("value", [None, ""])
    def test_missing_path_is_reported_as_none(self, value):
        assert redact_path(value) == "<none>"
