"""Coverage for :mod:`app.security_bootstrap`.

Pins the four resolution paths of :func:`ensure_overlay_server_token`
plus the open-scoreboard warning:

1. ``OVERLAY_SERVER_TOKEN_DISABLED=true`` → returns ``None`` and
   logs CRITICAL; ``os.environ`` is not touched.
2. ``OVERLAY_SERVER_TOKEN`` already set → returned verbatim.
3. Persisted file exists → loaded and injected into ``os.environ``.
4. Nothing set, nothing persisted → mint a fresh token, persist with
   ``0o600`` permissions, inject into ``os.environ``.
"""

from __future__ import annotations

import logging
import os
import stat
from pathlib import Path

import pytest

from app import security_bootstrap


@pytest.fixture(autouse=True)
def _reset_env(monkeypatch):
    monkeypatch.delenv("OVERLAY_SERVER_TOKEN", raising=False)
    monkeypatch.delenv("OVERLAY_SERVER_TOKEN_DISABLED", raising=False)
    monkeypatch.delenv("SCOREBOARD_USERS", raising=False)
    monkeypatch.delenv("SCOREBOARD_USERS_DISABLED", raising=False)


@pytest.fixture
def isolated_data_dir(tmp_path, monkeypatch):
    """Redirect the bootstrap's data dir to a per-test tmp dir.

    Avoids touching the repo's real ``data/`` directory and lets us
    inspect the persisted token file directly.
    """
    monkeypatch.setattr(security_bootstrap, "_data_dir", lambda: str(tmp_path))
    return tmp_path


# ---------------------------------------------------------------------------
# Path 1 — explicit opt-out
# ---------------------------------------------------------------------------


def test_explicit_opt_out_returns_none(isolated_data_dir, monkeypatch, caplog):
    monkeypatch.setenv("OVERLAY_SERVER_TOKEN_DISABLED", "true")
    with caplog.at_level(logging.CRITICAL, logger="app.security_bootstrap"):
        result = security_bootstrap.ensure_overlay_server_token()
    assert result is None
    # Env var must not be set even by mistake — the operator chose
    # fail-open and the rest of the app gates on emptiness.
    assert os.environ.get("OVERLAY_SERVER_TOKEN") is None
    # Persisted file must not be created either.
    assert not (isolated_data_dir / ".overlay_server_token").exists()
    # The opt-out is logged at CRITICAL so it surfaces in the startup tail.
    assert any("UNAUTHENTICATED" in rec.message for rec in caplog.records)


@pytest.mark.parametrize("flag", ["1", "true", "TRUE", "yes", "on"])
def test_opt_out_accepts_truthy_aliases(flag, isolated_data_dir, monkeypatch):
    monkeypatch.setenv("OVERLAY_SERVER_TOKEN_DISABLED", flag)
    assert security_bootstrap.ensure_overlay_server_token() is None


# ---------------------------------------------------------------------------
# Path 2 — already configured
# ---------------------------------------------------------------------------


def test_existing_env_var_is_passthrough(isolated_data_dir, monkeypatch):
    monkeypatch.setenv("OVERLAY_SERVER_TOKEN", "operator-supplied")
    result = security_bootstrap.ensure_overlay_server_token()
    assert result == "operator-supplied"
    assert os.environ["OVERLAY_SERVER_TOKEN"] == "operator-supplied"
    # Pre-set tokens must not be persisted — operator already manages
    # the value via env, persisting would shadow a future change.
    assert not (isolated_data_dir / ".overlay_server_token").exists()


def test_whitespace_only_env_treated_as_unset(isolated_data_dir, monkeypatch):
    monkeypatch.setenv("OVERLAY_SERVER_TOKEN", "   ")
    result = security_bootstrap.ensure_overlay_server_token()
    # Falls through to mint a fresh token rather than honouring "   ".
    assert result is not None and len(result) > 10
    assert os.environ["OVERLAY_SERVER_TOKEN"] == result


# ---------------------------------------------------------------------------
# Path 3 — persisted file
# ---------------------------------------------------------------------------


def test_persisted_token_is_loaded(isolated_data_dir, monkeypatch):
    persisted = isolated_data_dir / ".overlay_server_token"
    persisted.write_text("from-disk-token", encoding="utf-8")
    result = security_bootstrap.ensure_overlay_server_token()
    assert result == "from-disk-token"
    assert os.environ["OVERLAY_SERVER_TOKEN"] == "from-disk-token"


def test_persisted_token_with_trailing_whitespace_is_trimmed(
    isolated_data_dir, monkeypatch,
):
    persisted = isolated_data_dir / ".overlay_server_token"
    persisted.write_text("trimmed-token\n", encoding="utf-8")
    assert security_bootstrap.ensure_overlay_server_token() == "trimmed-token"


def test_empty_persisted_file_falls_through_to_generation(
    isolated_data_dir, monkeypatch,
):
    persisted = isolated_data_dir / ".overlay_server_token"
    persisted.write_text("", encoding="utf-8")
    result = security_bootstrap.ensure_overlay_server_token()
    assert result is not None and len(result) > 10
    # The empty file should have been overwritten with the new token.
    assert persisted.read_text(encoding="utf-8") == result


# ---------------------------------------------------------------------------
# Path 4 — auto-generation
# ---------------------------------------------------------------------------


def test_auto_generates_persists_and_sets_env(isolated_data_dir):
    result = security_bootstrap.ensure_overlay_server_token()
    assert result is not None
    assert len(result) >= 32  # token_urlsafe(32) → ~43 chars
    assert os.environ["OVERLAY_SERVER_TOKEN"] == result
    persisted = isolated_data_dir / ".overlay_server_token"
    assert persisted.exists()
    assert persisted.read_text(encoding="utf-8") == result


def test_persisted_file_has_owner_only_permissions(isolated_data_dir):
    security_bootstrap.ensure_overlay_server_token()
    persisted = isolated_data_dir / ".overlay_server_token"
    mode = persisted.stat().st_mode
    # Group and other bits must be cleared — the token is a credential.
    assert not (mode & stat.S_IRGRP)
    assert not (mode & stat.S_IWGRP)
    assert not (mode & stat.S_IROTH)
    assert not (mode & stat.S_IWOTH)


def test_subsequent_calls_are_idempotent(isolated_data_dir):
    """A second call must reuse the persisted token rather than rotating it."""
    first = security_bootstrap.ensure_overlay_server_token()
    # Simulate a process restart by clearing the env var only — the
    # file on disk should drive the next resolution.
    del os.environ["OVERLAY_SERVER_TOKEN"]
    second = security_bootstrap.ensure_overlay_server_token()
    assert first == second


def test_generation_failure_to_persist_still_returns_token(
    isolated_data_dir, monkeypatch, caplog,
):
    """If the data dir is unwritable, the in-memory token still works."""
    def fail_write(path: Path, token: str) -> bool:
        return False

    monkeypatch.setattr(security_bootstrap, "_write_persisted_token", fail_write)
    with caplog.at_level(logging.WARNING, logger="app.security_bootstrap"):
        result = security_bootstrap.ensure_overlay_server_token()
    assert result is not None
    assert os.environ["OVERLAY_SERVER_TOKEN"] == result
    assert any("could not persist" in rec.message.lower()
               for rec in caplog.records)


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------


def test_run_security_bootstrap_swallows_exceptions(monkeypatch, caplog):
    """A failure in one bootstrap step must not block startup."""
    def boom() -> None:
        raise RuntimeError("simulated")

    monkeypatch.setattr(
        security_bootstrap, "ensure_overlay_server_token", boom,
    )
    monkeypatch.setattr(
        security_bootstrap, "ensure_session_secret", boom,
    )
    with caplog.at_level(logging.ERROR, logger="app.security_bootstrap"):
        security_bootstrap.run_security_bootstrap()
    # Both failures should have been logged via logger.exception.
    failure_records = [
        rec for rec in caplog.records if "failed" in rec.message.lower()
    ]
    assert len(failure_records) >= 2
