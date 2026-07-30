"""Focused coverage for the dedicated report capability signing key."""

from __future__ import annotations

from app.match_report.signing import make_signed_query, verify_signed_query


def test_dedicated_key_survives_session_secret_rotation(monkeypatch):
    monkeypatch.setenv("MATCH_REPORT_SIGNING_SECRET", "report-key")
    monkeypatch.setenv("SESSION_SECRET", "session-one")
    signed = make_signed_query("match-1", now=1_000)
    assert signed is not None

    monkeypatch.setenv("SESSION_SECRET", "session-two")
    assert verify_signed_query(
        "match-1",
        signed["exp"],
        signed["sig"],
        now=1_001,
    )


def test_rotating_report_key_revokes_report_capabilities(monkeypatch):
    monkeypatch.setenv("MATCH_REPORT_SIGNING_SECRET", "report-one")
    signed = make_signed_query("match-1", now=1_000)
    assert signed is not None

    monkeypatch.setenv("MATCH_REPORT_SIGNING_SECRET", "report-two")
    assert not verify_signed_query(
        "match-1",
        signed["exp"],
        signed["sig"],
        now=1_001,
    )


def test_session_secret_remains_a_bootstrap_failure_fallback(monkeypatch):
    monkeypatch.delenv("MATCH_REPORT_SIGNING_SECRET", raising=False)
    monkeypatch.setenv("SESSION_SECRET", "session-fallback")
    signed = make_signed_query("match-1", now=1_000)
    assert signed is not None
    assert verify_signed_query(
        "match-1",
        signed["exp"],
        signed["sig"],
        now=1_001,
    )
