"""Shareable control-link (control_token) coverage.

The control token lets an operator drive a board without logging in: it resolves
to the owning overlay's storage key, so it works across users sharing an ``oid``
and is revoked when regenerated.

Each test uses a distinct ``oid`` so no two tests ever share a storage key —
TestClients here are created without a ``with`` block (no lifespan shutdown), so
a shared skey could otherwise see a stale async overlay-push from a prior test.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import overlays_service
from app.api.session_manager import SessionManager
from app.bootstrap import create_app
from app.overlay_key import make_skey
from tests.conftest import login_client


@pytest.fixture(autouse=True)
def _isolate_sessions(clean_sessions):
    """Clear the process-global SessionManager around each test in this module."""
    yield


def _control_token(client: TestClient, oid: str) -> str:
    """Create an overlay as the logged-in user and return its control token."""
    r = client.post("/api/v1/overlays", json={"oid": oid})
    assert r.status_code == 201, r.text
    token = r.json()["control_token"]
    assert token
    return token


def test_overlay_payload_exposes_control_link(db_session):
    c = TestClient(create_app())
    login_client(c, db_session, username="owner")
    body = c.post("/api/v1/overlays", json={"oid": "ctl-pay"}).json()
    assert body["control_token"]
    assert body["control_url"].endswith(f"/board?c={body['control_token']}")


def test_operator_can_init_and_control_without_login(db_session):
    owner = TestClient(create_app())
    login_client(owner, db_session, username="owner")
    token = _control_token(owner, "ctl-init")

    # A fresh, unauthenticated client (no cookie) holding only the token.
    operator = TestClient(create_app())
    r = operator.post(f"/api/v1/session/init?c={token}", json={"oid": "ctl-init"})
    assert r.status_code == 200, r.text

    # The session was created under the OWNER's storage key, not the token.
    assert overlays_service.get_by_control_token(db_session, token) is not None
    assert SessionManager.get(make_skey(owner.test_user_id, "ctl-init")) is not None

    # The operator can score and read state purely via the token.
    assert operator.post(f"/api/v1/game/add-point?c={token}", json={"team": 1}).status_code == 200
    state = operator.get(f"/api/v1/state?c={token}")
    assert state.status_code == 200
    assert state.json()["team_1"]["scores"]["set_1"] == 1


def test_owner_score_visible_through_operator_token(db_session):
    """Owner and operator address the same board (same storage key)."""
    owner = TestClient(create_app())
    login_client(owner, db_session, username="owner")
    token = _control_token(owner, "ctl-view")

    owner.post("/api/v1/session/init", json={"oid": "ctl-view"})
    owner.post("/api/v1/game/add-point?oid=ctl-view", json={"team": 2})

    operator = TestClient(create_app())
    state = operator.get(f"/api/v1/state?c={token}").json()
    assert state["team_2"]["scores"]["set_1"] == 1


def test_invalid_token_is_rejected(db_session):
    operator = TestClient(create_app())
    assert operator.post("/api/v1/session/init?c=bogus", json={"oid": "x"}).status_code == 403
    assert operator.get("/api/v1/state?c=bogus").status_code == 403


def test_no_credential_is_unauthorized(db_session):
    """Without a token or cookie the control surface stays locked."""
    anon = TestClient(create_app())
    # Gate fires before session lookup → 401 (not 404).
    assert anon.get("/api/v1/state?oid=ctl-anon").status_code == 401


def test_regenerate_revokes_old_link(db_session):
    owner = TestClient(create_app())
    login_client(owner, db_session, username="owner")
    old = _control_token(owner, "ctl-regen")

    r = owner.post("/api/v1/overlays/ctl-regen/regenerate-control-token")
    assert r.status_code == 200, r.text
    new = r.json()["control_token"]
    assert new and new != old

    # Old link no longer resolves; the new one does.
    operator = TestClient(create_app())
    assert operator.get(f"/api/v1/state?c={old}").status_code == 403
    operator.post(f"/api/v1/session/init?c={new}", json={"oid": "ctl-regen"})
    assert operator.get(f"/api/v1/state?c={new}").status_code == 200


def test_token_separates_same_oid_across_users(db_session):
    alice = TestClient(create_app())
    login_client(alice, db_session, username="alice")
    alice_token = _control_token(alice, "ctl-sep")

    bob = TestClient(create_app())
    login_client(bob, db_session, username="bob")
    bob_token = _control_token(bob, "ctl-sep")

    assert alice_token != bob_token
    # Each token drives its own owner's board.
    op_a = TestClient(create_app())
    op_a.post(f"/api/v1/session/init?c={alice_token}", json={"oid": "ctl-sep"})
    op_a.post(f"/api/v1/game/add-point?c={alice_token}", json={"team": 1})

    op_b = TestClient(create_app())
    op_b.post(f"/api/v1/session/init?c={bob_token}", json={"oid": "ctl-sep"})

    assert op_a.get(f"/api/v1/state?c={alice_token}").json()["team_1"]["scores"]["set_1"] == 1
    assert op_b.get(f"/api/v1/state?c={bob_token}").json()["team_1"]["scores"].get("set_1", 0) == 0


def test_ws_accepts_control_token(db_session):
    owner = TestClient(create_app())
    login_client(owner, db_session, username="owner")
    token = _control_token(owner, "ctl-ws")
    owner.post(f"/api/v1/session/init?c={token}", json={"oid": "ctl-ws"})

    operator = TestClient(create_app())
    with operator.websocket_connect(f"/api/v1/ws?c={token}") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "state_update"


def test_ws_rejects_bad_control_token(db_session):
    operator = TestClient(create_app())
    try:
        with operator.websocket_connect("/api/v1/ws?c=bogus"):
            raise AssertionError("expected the socket to be rejected")
    except Exception:
        pass
