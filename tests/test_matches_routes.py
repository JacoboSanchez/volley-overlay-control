"""Owner-scoped delete + signed-share-URL on ``/api/v1/matches/{id}``.

These replace the legacy ``DELETE /matches/{id}`` + ``sign-url`` admin
endpoints (which were gated by ``OVERLAY_MANAGER_PASSWORD``) with cookie
ownership after the multi-user refactor.
"""
from __future__ import annotations

from urllib.parse import urlsplit

from fastapi.testclient import TestClient

from app.api import match_archive
from app.bootstrap import create_app
from app.overlay_key import make_skey
from tests.conftest import login_client


def _archive(user_id: int, oid: str = "liga") -> str:
    match_id = match_archive.archive_match(
        oid=make_skey(user_id, oid),
        final_state={"team_1": {"sets": 3}, "team_2": {"sets": 1}},
        customization={"Team 1 Name": "Home", "Team 2 Name": "Away"},
        winning_team=1, sets_limit=5,
    )
    assert match_id is not None
    return match_id


def test_owner_can_delete_own_match(db_session):
    c = TestClient(create_app())
    login_client(c, db_session, username="owner")
    match_id = _archive(c.test_user_id)
    assert match_archive.load_match(match_id) is not None
    assert c.delete(f"/api/v1/matches/{match_id}").status_code == 204
    assert match_archive.load_match(match_id) is None


def test_non_owner_cannot_delete(db_session):
    owner = TestClient(create_app())
    login_client(owner, db_session, username="owner")
    match_id = _archive(owner.test_user_id)
    intruder = TestClient(create_app())
    login_client(intruder, db_session, username="intruder")
    assert intruder.delete(f"/api/v1/matches/{match_id}").status_code == 404
    assert match_archive.load_match(match_id) is not None


def test_sign_url_opens_report_without_a_cookie(db_session, monkeypatch):
    monkeypatch.delenv("MATCH_REPORT_PUBLIC", raising=False)
    owner = TestClient(create_app())
    login_client(owner, db_session, username="owner")
    match_id = _archive(owner.test_user_id)

    resp = owner.post(f"/api/v1/matches/{match_id}/sign-url")
    assert resp.status_code == 200, resp.text
    parts = urlsplit(resp.json()["url"])
    rel = f"{parts.path}?{parts.query}"

    # A brand-new, cookie-less client can read the report via the capability.
    anon = TestClient(create_app())
    assert anon.get(rel).status_code == 200
    # …but not without the signature.
    assert anon.get(f"/match/{match_id}/report").status_code == 401


def test_non_owner_cannot_mint_sign_url(db_session):
    owner = TestClient(create_app())
    login_client(owner, db_session, username="owner")
    match_id = _archive(owner.test_user_id)
    intruder = TestClient(create_app())
    login_client(intruder, db_session, username="intruder")
    assert intruder.post(f"/api/v1/matches/{match_id}/sign-url").status_code == 404
