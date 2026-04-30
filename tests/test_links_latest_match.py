"""Tests for the ``latest_match_report`` field in ``GET /api/v1/links``.

The field is added by ``app/api/routes/overlays.py`` only when:

* the env var ``MATCH_REPORT_PUBLIC`` is truthy (so the URL is
  shareable without an admin token), and
* there is at least one archived match for the session's OID.

Otherwise the field is omitted — the control UI does not have access
to ``OVERLAY_MANAGER_PASSWORD`` and surfacing a token-bearing URL
would invite copy-paste leaks.
"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api import match_archive
from app.api.session_manager import SessionManager
from app.bootstrap import create_app
from app.state import State
from tests.conftest import load_fixture

pytestmark = pytest.mark.usefixtures("clean_sessions")


@pytest.fixture
def client():
    with TestClient(create_app()) as c:
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


def _init_session(client, oid: str = "links-oid"):
    response = client.post("/api/v1/session/init", json={"oid": oid})
    assert response.status_code == 200


class TestLatestMatchReportLink:
    def test_omitted_when_public_disabled(
            self, client, fake_backend_cls, monkeypatch):
        monkeypatch.delenv("MATCH_REPORT_PUBLIC", raising=False)
        _init_session(client)
        match_archive.archive_match(
            oid="links-oid", final_state={}, winning_team=1,
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
            oid="links-oid", final_state={}, winning_team=1,
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
        # Microsecond-resolution filenames mean back-to-back archives are
        # ordered deterministically.
        match_archive.archive_match(
            oid="links-oid", final_state={}, winning_team=1,
        )
        latest = match_archive.archive_match(
            oid="links-oid", final_state={}, winning_team=2,
        )
        response = client.get("/api/v1/links?oid=links-oid")
        url = response.json().get("latest_match_report")
        assert url is not None
        assert url.endswith(f"/match/{latest}/report")

    def test_other_oids_archives_do_not_leak(
            self, client, fake_backend_cls, monkeypatch):
        monkeypatch.setenv("MATCH_REPORT_PUBLIC", "true")
        # Archive a match for a different OID — should not appear in our links.
        match_archive.archive_match(
            oid="someone-else", final_state={}, winning_team=1,
        )
        _init_session(client, oid="links-oid")
        response = client.get("/api/v1/links?oid=links-oid")
        assert "latest_match_report" not in response.json()
        # SessionManager cleanup is handled by the autouse clean_sessions fixture.
        SessionManager.remove("someone-else")
