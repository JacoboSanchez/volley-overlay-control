"""get_session / cookie-auth dependency behaviour (Phase 3 cutover).

Replaces the old SCOREBOARD_USERS Bearer + ``check_oid_access`` tests: the
scoreboard API is now cookie-authenticated and a session is addressed by the
per-user storage key, so a user can only reach sessions they initialised and
two users may drive the same ``oid`` in isolation.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import login_client


def _init(client, oid="liga"):
    return client.post("/api/v1/session/init", json={"oid": oid})


def test_unauthenticated_api_is_rejected(app_client):
    assert app_client.post("/api/v1/session/init", json={"oid": "liga"}).status_code == 401
    assert app_client.get("/api/v1/state?oid=liga").status_code == 401


def test_init_then_state_for_owner(auth_client):
    assert _init(auth_client).status_code == 200
    assert auth_client.get("/api/v1/state?oid=liga").status_code == 200


def test_state_without_init_is_404(auth_client):
    # Authenticated but no session yet for this oid.
    assert auth_client.get("/api/v1/state?oid=neverinit").status_code == 404


def test_two_users_share_an_oid_in_isolation(app_client, db_session):
    """Headline guarantee: same oid, two users, fully independent boards."""
    alice = login_client(app_client, db_session, "alice")
    assert _init(alice, "liga").status_code == 200
    assert alice.post("/api/v1/game/add-point?oid=liga", json={"team": 1}).status_code == 200

    bob = login_client(TestClient(app_client.app), db_session, "bob")
    # Bob's "liga" is a different board — no session until he inits.
    assert bob.get("/api/v1/state?oid=liga").status_code == 404
    assert _init(bob, "liga").status_code == 200

    alice_state = alice.get("/api/v1/state?oid=liga").json()
    bob_state = bob.get("/api/v1/state?oid=liga").json()
    assert alice_state["team_1"]["scores"].get("set_1", 0) == 1
    assert bob_state["team_1"]["scores"].get("set_1", 0) == 0


def test_matches_list_does_not_leak_other_users_with_malformed_oid(app_client, db_session):
    """Regression (IDOR): a malformed ?oid must not bypass per-user scoping
    and dump every user's archived matches."""
    from app.api import match_archive
    from app.overlay_key import make_skey

    alice = login_client(app_client, db_session, "alice")
    # Archive a match owned by alice.
    match_archive.archive_match(
        oid=make_skey(alice.test_user_id, "liga"), final_state={}, winning_team=1,
    )
    bob = login_client(TestClient(app_client.app), db_session, "bob")

    # A malformed oid makes make_skey produce an invalid storage key; the
    # route must still return nothing for bob (not alice's match).
    for bad in ("a:b", "x" * 200, "../etc"):
        resp = bob.get(f"/api/v1/matches?oid={bad}")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0, f"leaked for oid={bad!r}"
    # And bob's own (empty) listing is empty.
    assert bob.get("/api/v1/matches").json()["count"] == 0
    # alice still sees her own match.
    assert alice.get("/api/v1/matches?oid=liga").json()["count"] == 1
