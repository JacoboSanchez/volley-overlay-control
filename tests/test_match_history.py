"""Tests for the public per-overlay match-history page
(``GET /matches/{public_token}``)."""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api import match_archive
from app.bootstrap import create_app
from app.db.models.overlay import UserOverlay
from app.overlay_key import make_skey
from app.state import State
from tests.conftest import load_fixture, login_client

pytestmark = pytest.mark.usefixtures("clean_sessions")


@pytest.fixture
def client(db_session):
    with TestClient(create_app()) as c:
        login_client(c, db_session)
        yield c


@pytest.fixture
def fake_backend_cls():
    fake = MagicMock()
    fake.validate_and_store_model_for_oid.return_value = State.OIDStatus.VALID
    fake.init_ws_client.return_value = None
    fake.fetch_output_token.return_value = None
    fake.get_current_model.return_value = load_fixture("base_model")
    fake.get_current_customization.return_value = load_fixture("base_customization")
    fake.is_visible.return_value = True
    fake.is_custom_overlay.return_value = False
    with patch("app.api.routes.session.Backend", return_value=fake):
        yield fake


def _token(db_session, user_id, oid):
    ov = db_session.execute(
        select(UserOverlay).where(
            UserOverlay.user_id == user_id, UserOverlay.oid == oid,
        )
    ).scalar_one_or_none()
    return ov.public_token if ov else None


def _setup(client, db_session, oid="hist-oid", n=2):
    client.post("/api/v1/session/init", json={"oid": oid})
    skey = make_skey(client.test_user_id, oid)
    for i in range(n):
        match_archive.archive_match(
            oid=skey,
            final_state={
                "team_1": {"sets": 3}, "team_2": {"sets": i},
            },
            winning_team=1,
        )
    return _token(db_session, client.test_user_id, oid)


class TestMatchHistoryPage:
    def test_unknown_token_404(self, client, fake_backend_cls):
        assert client.get("/matches/nope-not-a-token").status_code == 404

    def test_lists_matches_when_public(
            self, client, db_session, fake_backend_cls, monkeypatch):
        monkeypatch.setenv("MATCH_REPORT_PUBLIC", "true")
        token = _setup(client, db_session, n=2)
        assert token is not None
        resp = client.get(f"/matches/{token}")
        assert resp.status_code == 200
        assert "Open report" in resp.text
        # One report link per archived match.
        assert resp.text.count("/report?lang=") == 2

    def test_requires_auth_when_not_public(
            self, client, db_session, fake_backend_cls, monkeypatch):
        monkeypatch.delenv("MATCH_REPORT_PUBLIC", raising=False)
        token = _setup(client, db_session, n=1)
        # A fresh client with no session cookie cannot read a gated history.
        with TestClient(create_app()) as anon:
            assert anon.get(f"/matches/{token}").status_code == 401

    def test_owner_can_view_when_not_public(
            self, client, db_session, fake_backend_cls, monkeypatch):
        monkeypatch.delenv("MATCH_REPORT_PUBLIC", raising=False)
        token = _setup(client, db_session, n=1)
        assert client.get(f"/matches/{token}").status_code == 200

    def test_sort_and_pagination_params_accepted(
            self, client, db_session, fake_backend_cls, monkeypatch):
        monkeypatch.setenv("MATCH_REPORT_PUBLIC", "true")
        token = _setup(client, db_session, n=3)
        resp = client.get(
            f"/matches/{token}?sort=duration&dir=asc&page=1"
        )
        assert resp.status_code == 200

    def test_filters_by_mode(
            self, client, db_session, fake_backend_cls, monkeypatch):
        monkeypatch.setenv("MATCH_REPORT_PUBLIC", "true")
        client.post("/api/v1/session/init", json={"oid": "hist-mode"})
        skey = make_skey(client.test_user_id, "hist-mode")
        match_archive.archive_match(
            oid=skey, winning_team=1,
            final_state={"config": {"mode": "beach"},
                         "team_1": {"sets": 2}, "team_2": {"sets": 0}},
        )
        match_archive.archive_match(
            oid=skey, winning_team=1,
            final_state={"config": {"mode": "table_tennis"},
                         "team_1": {"sets": 3}, "team_2": {"sets": 1}},
        )
        token = _token(db_session, client.test_user_id, "hist-mode")
        # No filter → both matches.
        assert client.get(f"/matches/{token}").text.count("/report?lang=") == 2
        # Beach only.
        assert client.get(
            f"/matches/{token}?mode=beach"
        ).text.count("/report?lang=") == 1
        # Table tennis only.
        assert client.get(
            f"/matches/{token}?mode=table_tennis"
        ).text.count("/report?lang=") == 1
        # Unknown mode falls back to "all".
        assert client.get(
            f"/matches/{token}?mode=bogus"
        ).text.count("/report?lang=") == 2

    def test_filters_by_day(
            self, client, db_session, fake_backend_cls, monkeypatch):
        from datetime import datetime
        monkeypatch.setenv("MATCH_REPORT_PUBLIC", "true")
        client.post("/api/v1/session/init", json={"oid": "hist-day"})
        skey = make_skey(client.test_user_id, "hist-day")
        match_archive.archive_match(
            oid=skey, winning_team=1,
            final_state={"team_1": {"sets": 2}, "team_2": {"sets": 0}},
        )
        token = _token(db_session, client.test_user_id, "hist-day")
        # Server-local "today" — matches the page's local-time day key.
        today = datetime.now().strftime("%Y-%m-%d")
        # The archived match's day → 1 result; a different day → none.
        assert client.get(
            f"/matches/{token}?day={today}"
        ).text.count("/report?lang=") == 1
        assert client.get(
            f"/matches/{token}?day=2000-01-01"
        ).text.count("/report?lang=") == 0
        # Malformed day is ignored (shows everything).
        assert client.get(
            f"/matches/{token}?day=not-a-date"
        ).text.count("/report?lang=") == 1
        # The page renders a date picker.
        assert "type='date'" in client.get(f"/matches/{token}").text

    def test_empty_history_renders(
            self, client, db_session, fake_backend_cls, monkeypatch):
        monkeypatch.setenv("MATCH_REPORT_PUBLIC", "true")
        client.post("/api/v1/session/init", json={"oid": "hist-empty"})
        token = _token(db_session, client.test_user_id, "hist-empty")
        resp = client.get(f"/matches/{token}")
        assert resp.status_code == 200
        assert "No archived matches yet." in resp.text
