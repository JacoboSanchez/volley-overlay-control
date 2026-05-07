"""Unit tests for ``app.api.dependencies``.

Existing tests exercise these helpers indirectly through the routes;
this file covers the branches the route tests skip (strict-OID mode,
non-dict per-user config, the pure permission check independent of any
``GameSession``).
"""

from __future__ import annotations

import json

import pytest
from fastapi import HTTPException

from app.api.dependencies import (
    _strict_oid_access_enabled,
    check_oid_access,
    get_current_username,
)
from app.authentication import PasswordAuthenticator

# ---------------------------------------------------------------------------
# _strict_oid_access_enabled
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("raw", ["1", "true", "True", "yes", "on", "T"])
def test_strict_oid_access_truthy(raw, monkeypatch):
    monkeypatch.setenv("STRICT_OID_ACCESS", raw)
    assert _strict_oid_access_enabled() is True


@pytest.mark.parametrize("raw", ["", "0", "false", "no", "off", "anything-else"])
def test_strict_oid_access_falsy(raw, monkeypatch):
    monkeypatch.setenv("STRICT_OID_ACCESS", raw)
    assert _strict_oid_access_enabled() is False


def test_strict_oid_access_unset_defaults_off(monkeypatch):
    monkeypatch.delenv("STRICT_OID_ACCESS", raising=False)
    assert _strict_oid_access_enabled() is False


# ---------------------------------------------------------------------------
# check_oid_access
# ---------------------------------------------------------------------------


@pytest.fixture
def configured_users(monkeypatch):
    """Configure SCOREBOARD_USERS with one OID-bound user and one open user.

    The cache on ``PasswordAuthenticator`` is reset so the new env var
    takes effect immediately.
    """
    monkeypatch.setenv(
        "SCOREBOARD_USERS",
        json.dumps({
            "alice": {"password": "alice-pw", "control": "ovl-alice"},
            "bob":   {"password": "bob-pw"},
            "broken": "i-am-not-a-dict",
        }),
    )
    PasswordAuthenticator._cached_users = None
    PasswordAuthenticator._cached_users_raw = None
    yield
    PasswordAuthenticator._cached_users = None
    PasswordAuthenticator._cached_users_raw = None


def test_check_oid_access_skips_when_auth_disabled(monkeypatch):
    """No SCOREBOARD_USERS set → check is a no-op."""
    monkeypatch.delenv("SCOREBOARD_USERS", raising=False)
    PasswordAuthenticator._cached_users = None
    PasswordAuthenticator._cached_users_raw = None
    # Whatever we pass should be accepted.
    check_oid_access("", "any-oid")
    check_oid_access("Bearer garbage", "any-oid")


def test_check_oid_access_missing_header(configured_users):
    with pytest.raises(HTTPException) as exc:
        check_oid_access("", "ovl-alice")
    assert exc.value.status_code == 401
    assert exc.value.headers is not None
    assert exc.value.headers.get("WWW-Authenticate") == 'Bearer realm="scoreboard"'


def test_check_oid_access_invalid_token(configured_users):
    with pytest.raises(HTTPException) as exc:
        check_oid_access("Bearer not-a-real-token", "ovl-alice")
    assert exc.value.status_code == 403


def test_check_oid_access_allowed_oid(configured_users):
    # Alice's password IS her API key in the un-hashed config flavour.
    check_oid_access("Bearer alice-pw", "ovl-alice")


def test_check_oid_access_rejects_mismatched_oid(configured_users):
    with pytest.raises(HTTPException) as exc:
        check_oid_access("Bearer alice-pw", "ovl-someone-else")
    assert exc.value.status_code == 403


def test_check_oid_access_no_control_lenient_mode(configured_users, monkeypatch):
    """Bob has no ``control`` field; default mode allows any OID."""
    monkeypatch.delenv("STRICT_OID_ACCESS", raising=False)
    check_oid_access("Bearer bob-pw", "any-oid")


def test_check_oid_access_no_control_strict_mode(configured_users, monkeypatch):
    """With ``STRICT_OID_ACCESS=true``, missing ``control`` denies."""
    monkeypatch.setenv("STRICT_OID_ACCESS", "true")
    with pytest.raises(HTTPException) as exc:
        check_oid_access("Bearer bob-pw", "any-oid")
    assert exc.value.status_code == 403


def test_check_oid_access_non_dict_user_entry(configured_users):
    """A malformed per-user value (string instead of dict) is treated as
    "no constraint"; the call must not crash on ``.get(...)``."""
    # The ``broken`` user has password "i-am-not-a-dict"; that string
    # cannot be a valid Bearer token via ``check_api_key`` so the call
    # falls through 403 — but importantly, no AttributeError.
    with pytest.raises(HTTPException) as exc:
        check_oid_access("Bearer i-am-not-a-dict", "any-oid")
    assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# get_current_username
# ---------------------------------------------------------------------------


def test_get_current_username_none_for_missing_header():
    assert get_current_username(None) is None
    assert get_current_username("") is None


def test_get_current_username_returns_user(configured_users):
    assert get_current_username("Bearer alice-pw") == "alice"
    assert get_current_username("Bearer bob-pw") == "bob"


def test_get_current_username_unknown_token_returns_none(configured_users):
    assert get_current_username("Bearer not-a-key") is None
