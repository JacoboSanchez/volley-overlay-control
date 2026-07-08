"""End-to-end coverage for the per-user overlay routes (/api/v1/overlays).

Focus: the DELETE cascade (overlay row + live session + local state + archived
matches) and cross-user isolation when two users own the same oid.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.api import match_archive
from app.bootstrap import create_app
from app.overlay_key import make_skey
from tests.conftest import login_client


def _archive(user_id: int, oid: str) -> str:
    match_id = match_archive.archive_match(
        oid=make_skey(user_id, oid),
        final_state={"team_1": {"sets": 3}, "team_2": {"sets": 0}},
        customization={"Team 1 Name": "Home", "Team 2 Name": "Away"},
        winning_team=1, sets_limit=5,
    )
    assert match_id is not None
    return match_id


def test_owner_delete_cascades_overlay_and_matches(db_session):
    c = TestClient(create_app())
    login_client(c, db_session, username="owner")

    assert c.post("/api/v1/overlays", json={"oid": "liga"}).status_code == 201
    _archive(c.test_user_id, "liga")
    assert match_archive.list_matches(oid=make_skey(c.test_user_id, "liga"))

    assert c.delete("/api/v1/overlays/liga").status_code == 200
    # Gone from the caller's listing…
    assert all(o["oid"] != "liga" for o in c.get("/api/v1/overlays").json())
    # …and the archived matches were cleaned up.
    assert match_archive.list_matches(oid=make_skey(c.test_user_id, "liga")) == []


def test_delete_unknown_overlay_is_404(db_session):
    c = TestClient(create_app())
    login_client(c, db_session, username="owner")
    assert c.delete("/api/v1/overlays/nope").status_code == 404


def test_non_owner_cannot_delete_same_named_overlay(db_session):
    alice = TestClient(create_app())
    login_client(alice, db_session, username="alice")
    assert alice.post("/api/v1/overlays", json={"oid": "liga"}).status_code == 201

    bob = TestClient(create_app())
    login_client(bob, db_session, username="bob")
    # Bob has no "liga" overlay; deleting it must 404, not touch Alice's.
    assert bob.delete("/api/v1/overlays/liga").status_code == 404
    assert any(o["oid"] == "liga" for o in alice.get("/api/v1/overlays").json())
