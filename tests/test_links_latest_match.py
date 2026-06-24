"""Tests for the ``latest_match_report`` field in ``GET /api/v1/links``.

The field is added by ``app/api/routes/overlays.py`` only when:

* the env var ``MATCH_REPORT_PUBLIC`` is truthy, and
* there is at least one archived match for the session's storage key.

Archives are keyed per-user (``<user_id>:<oid>``) post-cutover, so the
"other oids don't leak" guarantee now also covers other *users*.
"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api import match_archive
from app.api.session_manager import SessionManager
from app.bootstrap import create_app
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


def _skey(client, oid="links-oid"):
    return make_skey(client.test_user_id, oid)


def _init_session(client, oid: str = "links-oid"):
    response = client.post("/api/v1/session/init", json={"oid": oid})
    assert response.status_code == 200


class TestLatestMatchReportLink:
    def test_omitted_when_public_disabled(
            self, client, fake_backend_cls, monkeypatch):
        monkeypatch.delenv("MATCH_REPORT_PUBLIC", raising=False)
        _init_session(client)
        match_archive.archive_match(
            oid=_skey(client), final_state={}, winning_team=1,
        )
        response = client.get("/api/v1/links?oid=links-oid")
        assert response.status_code == 200
        assert "latest_match_report" not in response.json()

    def test_omitted_when_no_archived_match(
            self, client, fake_backend_cls, monkeypatch):
        monkeypatch.setenv("MATCH_REPORT_PUBLIC", "true")
        _init_session(client)
        response = client.get("/api/v1/links?oid=links-oid")
        assert response.status_code == 200
        assert "latest_match_report" not in response.json()

    def test_returns_url_when_public_and_archive_exists(
            self, client, fake_backend_cls, monkeypatch):
        monkeypatch.setenv("MATCH_REPORT_PUBLIC", "true")
        _init_session(client)
        match_id = match_archive.archive_match(
            oid=_skey(client), final_state={}, winning_team=1,
        )
        response = client.get("/api/v1/links?oid=links-oid")
        assert response.status_code == 200
        url = response.json().get("latest_match_report")
        assert url is not None
        assert url.endswith(f"/match/{match_id}/report")

    def test_returns_newest_when_multiple(
            self, client, fake_backend_cls, monkeypatch):
        monkeypatch.setenv("MATCH_REPORT_PUBLIC", "true")
        _init_session(client)
        match_archive.archive_match(
            oid=_skey(client), final_state={}, winning_team=1,
        )
        latest = match_archive.archive_match(
            oid=_skey(client), final_state={}, winning_team=2,
        )
        response = client.get("/api/v1/links?oid=links-oid")
        url = response.json().get("latest_match_report")
        assert url is not None
        assert url.endswith(f"/match/{latest}/report")

    def test_other_oids_archives_do_not_leak(
            self, client, fake_backend_cls, monkeypatch):
        monkeypatch.setenv("MATCH_REPORT_PUBLIC", "true")
        match_archive.archive_match(
            oid=make_skey(client.test_user_id, "someone-else"),
            final_state={}, winning_team=1,
        )
        _init_session(client, oid="links-oid")
        response = client.get("/api/v1/links?oid=links-oid")
        assert "latest_match_report" not in response.json()
        assert "match_history" not in response.json()

    def test_match_history_link_present_when_public_and_archived(
            self, client, fake_backend_cls, monkeypatch):
        # The public history page is keyed by the overlay's unguessable
        # public_token and points at the real ``/matches/{token}`` route
        # (the old ``/matches/index.html`` page was removed in the
        # multi-user refactor).
        monkeypatch.setenv("MATCH_REPORT_PUBLIC", "true")
        _init_session(client, oid="links-history")
        match_archive.archive_match(
            oid=_skey(client, "links-history"), final_state={}, winning_team=1,
        )
        response = client.get("/api/v1/links?oid=links-history")
        body = response.json()
        assert body.get("latest_match_report") is not None
        history = body.get("match_history")
        assert history is not None
        assert "/matches/" in history

    def test_match_history_link_omitted_when_no_archives(
            self, client, fake_backend_cls, monkeypatch):
        monkeypatch.setenv("MATCH_REPORT_PUBLIC", "true")
        _init_session(client, oid="links-no-history")
        response = client.get("/api/v1/links?oid=links-no-history")
        body = response.json()
        assert "match_history" not in body

    def test_match_history_link_omitted_when_public_disabled(
            self, client, fake_backend_cls, monkeypatch):
        monkeypatch.delenv("MATCH_REPORT_PUBLIC", raising=False)
        _init_session(client, oid="links-private")
        match_archive.archive_match(
            oid=_skey(client, "links-private"), final_state={}, winning_team=1,
        )
        response = client.get("/api/v1/links?oid=links-private")
        assert "match_history" not in response.json()
        _ = SessionManager
