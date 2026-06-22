"""Coverage for :mod:`app.security_bootstrap`.

Pins the resolution paths of :func:`ensure_session_secret`:

1. ``SESSION_SECRET`` already set → returned verbatim.
2. Persisted file exists → loaded and injected into ``os.environ``.
3. Nothing set, nothing persisted → mint a fresh secret, persist with
   ``0o600`` permissions, inject into ``os.environ``.
"""

from __future__ import annotations

import logging
import os
import stat
from pathlib import Path

import pytest

from app import security_bootstrap

_FILE = ".session_secret"


@pytest.fixture(autouse=True)
def _reset_env(monkeypatch):
    monkeypatch.delenv("SESSION_SECRET", raising=False)


@pytest.fixture
def isolated_data_dir(tmp_path, monkeypatch):
    """Redirect the bootstrap's data dir to a per-test tmp dir."""
    monkeypatch.setattr(security_bootstrap, "_data_dir", lambda: str(tmp_path))
    return tmp_path


# -- Path 1: already configured ---------------------------------------------


def test_existing_env_var_is_passthrough(isolated_data_dir, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "operator-supplied")
    result = security_bootstrap.ensure_session_secret()
    assert result == "operator-supplied"
    assert os.environ["SESSION_SECRET"] == "operator-supplied"
    # Pre-set secrets must not be persisted.
    assert not (isolated_data_dir / _FILE).exists()


def test_whitespace_only_env_treated_as_unset(isolated_data_dir, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "   ")
    result = security_bootstrap.ensure_session_secret()
    assert result is not None and len(result) > 10
    assert os.environ["SESSION_SECRET"] == result


# -- Path 2: persisted file -------------------------------------------------


def test_persisted_secret_is_loaded(isolated_data_dir):
    (isolated_data_dir / _FILE).write_text("from-disk", encoding="utf-8")
    result = security_bootstrap.ensure_session_secret()
    assert result == "from-disk"
    assert os.environ["SESSION_SECRET"] == "from-disk"


def test_persisted_secret_trailing_whitespace_is_trimmed(isolated_data_dir):
    (isolated_data_dir / _FILE).write_text("trimmed\n", encoding="utf-8")
    assert security_bootstrap.ensure_session_secret() == "trimmed"


def test_empty_persisted_file_falls_through_to_generation(isolated_data_dir):
    persisted = isolated_data_dir / _FILE
    persisted.write_text("", encoding="utf-8")
    result = security_bootstrap.ensure_session_secret()
    assert result is not None and len(result) > 10
    assert persisted.read_text(encoding="utf-8") == result


# -- Path 3: auto-generation ------------------------------------------------


def test_auto_generates_persists_and_sets_env(isolated_data_dir):
    result = security_bootstrap.ensure_session_secret()
    assert result is not None
    assert len(result) >= 32  # token_urlsafe(32) → ~43 chars
    assert os.environ["SESSION_SECRET"] == result
    persisted = isolated_data_dir / _FILE
    assert persisted.exists()
    assert persisted.read_text(encoding="utf-8") == result


def test_persisted_file_has_owner_only_permissions(isolated_data_dir):
    security_bootstrap.ensure_session_secret()
    mode = (isolated_data_dir / _FILE).stat().st_mode
    assert not (mode & stat.S_IRGRP)
    assert not (mode & stat.S_IWGRP)
    assert not (mode & stat.S_IROTH)
    assert not (mode & stat.S_IWOTH)


def test_subsequent_calls_are_idempotent(isolated_data_dir):
    first = security_bootstrap.ensure_session_secret()
    del os.environ["SESSION_SECRET"]  # simulate restart; file drives resolution
    second = security_bootstrap.ensure_session_secret()
    assert first == second


def test_generation_failure_to_persist_still_returns_secret(
    isolated_data_dir, monkeypatch, caplog,
):
    def fail_write(path: Path, token: str) -> bool:
        return False

    monkeypatch.setattr(security_bootstrap, "_write_persisted_token", fail_write)
    with caplog.at_level(logging.WARNING, logger="app.security_bootstrap"):
        result = security_bootstrap.ensure_session_secret()
    assert result is not None
    assert os.environ["SESSION_SECRET"] == result
    assert any("could not persist" in rec.message.lower() for rec in caplog.records)


# -- Top-level entry point --------------------------------------------------


def test_run_security_bootstrap_swallows_exceptions(monkeypatch, caplog):
    """A failure in a bootstrap step must not block startup."""
    def boom() -> None:
        raise RuntimeError("simulated")

    monkeypatch.setattr(security_bootstrap, "ensure_session_secret", boom)
    with caplog.at_level(logging.ERROR, logger="app.security_bootstrap"):
        security_bootstrap.run_security_bootstrap()
    assert any("failed" in rec.message.lower() for rec in caplog.records)
