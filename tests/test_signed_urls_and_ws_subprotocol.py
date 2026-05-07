"""Coverage for the H-4 query-string-secret hardening.

Two surfaces are pinned:

* :mod:`app.match_report_signing` — HMAC-signed match-report URLs
  and the corresponding admin endpoint
  ``POST /api/v1/admin/match/{match_id}/sign-url``. The admin
  password no longer needs to be on the URL line.
* :mod:`app.api.routes.websocket` — the ``/api/v1/ws`` route now
  prefers the Bearer subprotocol (``Sec-WebSocket-Protocol:
  bearer, <token>``) over the legacy ``?token=`` query param,
  echoing the chosen subprotocol back to the client during
  ``ws.accept`` so browser clients don't drop the connection.
"""

from __future__ import annotations

import json
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import match_report_signing
from app.admin import admin_router
from app.api.middleware import auth_rate_limit


@pytest.fixture(autouse=True)
def _reset_env(monkeypatch):
    monkeypatch.delenv("OVERLAY_MANAGER_PASSWORD", raising=False)
    monkeypatch.delenv("MATCH_REPORT_PUBLIC", raising=False)
    auth_rate_limit._reset_for_tests()
    yield
    auth_rate_limit._reset_for_tests()


# ---------------------------------------------------------------------------
# match_report_signing module
# ---------------------------------------------------------------------------


def test_signing_returns_none_when_admin_password_unset():
    assert match_report_signing.make_signed_query("m") is None


def test_signing_returns_none_for_verify_when_admin_password_unset():
    assert (
        match_report_signing.verify_signed_query("m", "100", "deadbeef")
        is False
    )


def test_signed_query_round_trips(monkeypatch):
    monkeypatch.setenv("OVERLAY_MANAGER_PASSWORD", "k")
    out = match_report_signing.make_signed_query("match-1", ttl_seconds=600)
    assert out is not None
    assert out["expires_at"] == out["exp"]
    assert match_report_signing.verify_signed_query(
        "match-1", out["exp"], out["sig"],
    )


def test_verify_rejects_expired(monkeypatch):
    monkeypatch.setenv("OVERLAY_MANAGER_PASSWORD", "k")
    out = match_report_signing.make_signed_query(
        "match-1", ttl_seconds=match_report_signing.MIN_TTL_SECONDS,
    )
    assert out is not None
    # Pretend we're far in the future.
    future = out["exp"] + 1
    assert (
        match_report_signing.verify_signed_query(
            "match-1", out["exp"], out["sig"], now=future,
        )
        is False
    )


def test_verify_rejects_tampered_match_id(monkeypatch):
    monkeypatch.setenv("OVERLAY_MANAGER_PASSWORD", "k")
    out = match_report_signing.make_signed_query("match-1", ttl_seconds=600)
    assert out is not None
    # Same exp + sig, different match_id → must fail.
    assert (
        match_report_signing.verify_signed_query(
            "match-2", out["exp"], out["sig"],
        )
        is False
    )


def test_verify_rejects_tampered_sig(monkeypatch):
    monkeypatch.setenv("OVERLAY_MANAGER_PASSWORD", "k")
    out = match_report_signing.make_signed_query("match-1", ttl_seconds=600)
    assert out is not None
    bad_sig = "0" * len(out["sig"])
    assert (
        match_report_signing.verify_signed_query(
            "match-1", out["exp"], bad_sig,
        )
        is False
    )


def test_verify_handles_malformed_inputs(monkeypatch):
    monkeypatch.setenv("OVERLAY_MANAGER_PASSWORD", "k")
    # Non-numeric exp.
    assert (
        match_report_signing.verify_signed_query("m", "not-a-number", "x")
        is False
    )
    # Empty sig.
    assert match_report_signing.verify_signed_query("m", 100, "") is False
    # None sig.
    assert match_report_signing.verify_signed_query("m", 100, None) is False
    # None exp.
    assert match_report_signing.verify_signed_query("m", None, "x") is False


def test_password_rotation_invalidates_old_signatures(monkeypatch):
    monkeypatch.setenv("OVERLAY_MANAGER_PASSWORD", "old")
    out = match_report_signing.make_signed_query("match-1", ttl_seconds=600)
    assert out is not None
    monkeypatch.setenv("OVERLAY_MANAGER_PASSWORD", "new")
    assert (
        match_report_signing.verify_signed_query(
            "match-1", out["exp"], out["sig"],
        )
        is False
    )


def test_clamp_ttl_bounds():
    assert (
        match_report_signing.clamp_ttl(-1)
        == match_report_signing.DEFAULT_TTL_SECONDS
    )
    assert (
        match_report_signing.clamp_ttl(0)
        == match_report_signing.DEFAULT_TTL_SECONDS
    )
    # Below floor → snapped up to MIN.
    assert (
        match_report_signing.clamp_ttl(1)
        == match_report_signing.MIN_TTL_SECONDS
    )
    # Above ceiling → snapped down to MAX.
    assert (
        match_report_signing.clamp_ttl(10**9)
        == match_report_signing.MAX_TTL_SECONDS
    )
    # ``None`` and garbage fall back to the default.
    assert (
        match_report_signing.clamp_ttl(None)
        == match_report_signing.DEFAULT_TTL_SECONDS
    )
    assert (
        match_report_signing.clamp_ttl("not-a-number")
        == match_report_signing.DEFAULT_TTL_SECONDS
    )


# ---------------------------------------------------------------------------
# Admin sign-url endpoint
# ---------------------------------------------------------------------------


@pytest.fixture
def admin_client(monkeypatch):
    monkeypatch.setenv("OVERLAY_MANAGER_PASSWORD", "admin-pw")
    app = FastAPI()
    app.include_router(admin_router)
    return TestClient(app)


def _admin_headers(pw: str = "admin-pw"):
    return {"Authorization": f"Bearer {pw}"}


def test_sign_url_requires_admin(admin_client):
    res = admin_client.post(
        "/api/v1/admin/match/m1/sign-url", json={},
    )
    assert res.status_code == 401


def test_sign_url_returns_capability_url(admin_client):
    res = admin_client.post(
        "/api/v1/admin/match/match-abc/sign-url",
        json={},
        headers=_admin_headers(),
    )
    assert res.status_code == 200
    body = res.json()
    assert body["url"].endswith(
        f"?exp={body['expires_at']}&sig=" + body["url"].rsplit("sig=", 1)[1],
    )
    # Crucial: the admin password must NOT appear in the URL.
    assert "admin-pw" not in body["url"]
    # And the URL is for the right match.
    assert "/match/match-abc/report" in body["url"]


def test_sign_url_respects_ttl(admin_client):
    res = admin_client.post(
        "/api/v1/admin/match/m1/sign-url",
        json={"ttl_seconds": 60},
        headers=_admin_headers(),
    )
    assert res.status_code == 200
    body = res.json()
    # Expires_in is bounded — we just minted it, should be near 60.
    assert 50 <= body["expires_in"] <= 60


def test_sign_url_rejects_out_of_range_ttl(admin_client):
    # Above MAX_TTL_SECONDS → 422 from Pydantic Field bound.
    res = admin_client.post(
        "/api/v1/admin/match/m1/sign-url",
        json={"ttl_seconds": 10**9},
        headers=_admin_headers(),
    )
    assert res.status_code == 422


# ---------------------------------------------------------------------------
# /match/{match_id}/report — signed URL access path
# ---------------------------------------------------------------------------


@pytest.fixture
def gated_match(monkeypatch):
    """Seed an archive entry that needs auth to read.

    Returns ``(client, match_id)``.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api import action_log, match_archive
    from app.match_report import match_report_router

    monkeypatch.setenv("OVERLAY_MANAGER_PASSWORD", "admin-pw")
    monkeypatch.delenv("MATCH_REPORT_PUBLIC", raising=False)

    action_log.append(
        "sig-oid", "add_point", {"team": 1, "undo": False},
        {"team_1": {"score": 1}},
    )
    match_id = match_archive.archive_match(
        oid="sig-oid",
        final_state={
            "current_set": 1,
            "team_1": {"sets": 1, "timeouts": 0, "scores": {"set_1": 25}},
            "team_2": {"sets": 0, "timeouts": 0, "scores": {"set_1": 20}},
        },
        customization={"Team 1 Name": "Home", "Team 2 Name": "Away"},
        started_at=time.time() - 100,
        winning_team=1,
        points_limit=25,
        points_limit_last_set=15,
        sets_limit=3,
    )
    app = FastAPI()
    app.include_router(match_report_router)
    return TestClient(app), match_id


def test_signed_url_grants_access_without_password(gated_match):
    client, match_id = gated_match
    out = match_report_signing.make_signed_query(match_id, ttl_seconds=600)
    assert out is not None

    res = client.get(
        f"/match/{match_id}/report",
        params={"exp": out["exp"], "sig": out["sig"]},
    )
    assert res.status_code == 200
    assert "Home" in res.text


def test_expired_signed_url_falls_back_to_password(gated_match):
    client, match_id = gated_match
    out = match_report_signing.make_signed_query(
        match_id, ttl_seconds=match_report_signing.MIN_TTL_SECONDS,
    )
    assert out is not None
    # Manually rewrite exp to the past.
    res = client.get(
        f"/match/{match_id}/report",
        params={"exp": int(time.time()) - 60, "sig": out["sig"]},
    )
    # Falls through to the require-admin-token branch — without a
    # Bearer header that's a 401.
    assert res.status_code == 401


def test_tampered_signature_is_rejected(gated_match):
    client, match_id = gated_match
    out = match_report_signing.make_signed_query(match_id, ttl_seconds=600)
    assert out is not None
    res = client.get(
        f"/match/{match_id}/report",
        params={"exp": out["exp"], "sig": "0" * len(out["sig"])},
    )
    assert res.status_code in (401, 403)


def test_signed_url_for_other_match_does_not_grant_access(gated_match):
    client, match_id = gated_match
    other = match_report_signing.make_signed_query("other-match", 600)
    assert other is not None
    res = client.get(
        f"/match/{match_id}/report",
        params={"exp": other["exp"], "sig": other["sig"]},
    )
    # The signature is for ``other-match``, not this match_id; the
    # signed-URL path must reject it and the request falls through to
    # the password-required branch (no Bearer header → 401/403).
    assert res.status_code in (401, 403)


# ---------------------------------------------------------------------------
# WebSocket Bearer subprotocol auth
# ---------------------------------------------------------------------------


@pytest.fixture
def ws_client(monkeypatch):
    """SCOREBOARD_USERS-protected app with a single user."""
    from fastapi import FastAPI

    from app.api import api_router
    from app.api.session_manager import SessionManager
    from app.api.ws_hub import WSHub

    SessionManager.clear()
    WSHub.clear()
    users = json.dumps({"alice": {"password": "alice-pw"}})
    monkeypatch.setenv("SCOREBOARD_USERS", users)
    app = FastAPI()
    app.include_router(api_router)
    client = TestClient(app)

    # Initialise a session so the WS endpoint reaches the auth check
    # before the SessionManager.get None branch.
    res = client.post(
        "/api/v1/session/init",
        json={"oid": "test_overlay"},
        headers={"Authorization": "Bearer alice-pw"},
    )
    assert res.status_code == 200, res.text

    yield client
    SessionManager.clear()
    WSHub.clear()


def test_ws_accepts_bearer_subprotocol(ws_client):
    # TestClient.websocket_connect supports the ``subprotocols`` arg
    # which becomes the ``Sec-WebSocket-Protocol`` header.
    with ws_client.websocket_connect(
        "/api/v1/ws?oid=test_overlay",
        subprotocols=["bearer", "alice-pw"],
    ) as ws:
        # Server must echo back the chosen subprotocol so the browser
        # accepts the connection.
        assert ws.accepted_subprotocol == "bearer"
        # Initial state_update should be delivered immediately.
        msg = ws.receive_json()
        assert msg["type"] == "state_update"


def test_ws_rejects_invalid_bearer_subprotocol(ws_client):
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect), ws_client.websocket_connect(
        "/api/v1/ws?oid=test_overlay",
        subprotocols=["bearer", "wrong-password"],
    ):
        pass


def test_ws_legacy_query_token_still_works(ws_client):
    """Legacy ?token= path is preserved so older CLI clients keep working."""
    with ws_client.websocket_connect(
        "/api/v1/ws?oid=test_overlay&token=alice-pw",
    ) as ws:
        # No subprotocol negotiated — ``accepted_subprotocol`` is None.
        assert ws.accepted_subprotocol is None
        msg = ws.receive_json()
        assert msg["type"] == "state_update"


def test_ws_subprotocol_takes_precedence_over_query(ws_client):
    """When both auth modes are present, the subprotocol wins.

    Pinning this avoids a regression where a future refactor reorders
    the resolution and silently downgrades a Bearer-subprotocol
    client to query-token semantics (e.g. logging the legacy path).
    """
    with ws_client.websocket_connect(
        "/api/v1/ws?oid=test_overlay&token=wrong-password",
        subprotocols=["bearer", "alice-pw"],
    ) as ws:
        assert ws.accepted_subprotocol == "bearer"
        msg = ws.receive_json()
        assert msg["type"] == "state_update"
