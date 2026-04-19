"""Integration tests for app/api/routes/* using FastAPI's TestClient.

Covers the HTTP and WebSocket surface end-to-end: session lifecycle, game
actions, session-not-found errors, and WSHub broadcast across multiple
clients. Backend HTTP dependencies are patched so no network traffic occurs.
"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.bootstrap import create_app
from app.api.session_manager import SessionManager
from app.state import State

from tests.conftest import load_fixture


pytestmark = pytest.mark.usefixtures("clean_sessions")


@pytest.fixture
def client():
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def fake_backend_cls():
    """Patch ``Backend`` in ``routes.session`` so no real HTTP is made."""
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


# ---------------------------------------------------------------------------
# /session/init
# ---------------------------------------------------------------------------

class TestSessionInit:
    def test_init_creates_session(self, client, fake_backend_cls):
        r = client.post("/api/v1/session/init", json={"oid": "abc"})
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert body["state"]["current_set"] == 1
        assert SessionManager.get("abc") is not None

    def test_init_returns_existing_session(self, client, fake_backend_cls):
        client.post("/api/v1/session/init", json={"oid": "abc"})
        fake_backend_cls.validate_and_store_model_for_oid.reset_mock()

        r = client.post("/api/v1/session/init", json={"oid": "abc"})
        assert r.status_code == 200
        # The second init should NOT re-validate the OID (short-circuit path).
        fake_backend_cls.validate_and_store_model_for_oid.assert_not_called()

    def test_init_invalid_oid_returns_error(self, client):
        with patch("app.api.routes.session.Backend") as backend_cls:
            inst = backend_cls.return_value
            inst.validate_and_store_model_for_oid.return_value = State.OIDStatus.INVALID
            r = client.post("/api/v1/session/init", json={"oid": "badoid"})
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is False
        assert "invalid" in (body.get("message") or "").lower()
        assert SessionManager.get("badoid") is None

    def test_init_rejects_malformed_oid(self, client):
        r = client.post("/api/v1/session/init", json={"oid": "has spaces"})
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# /game/* require a session
# ---------------------------------------------------------------------------

class TestGameRoutes:
    def test_add_point_404_without_session(self, client):
        r = client.post(
            "/api/v1/game/add-point?oid=missing",
            json={"team": 1},
        )
        assert r.status_code == 404

    def test_add_point_with_session(self, client, fake_backend_cls):
        client.post("/api/v1/session/init", json={"oid": "abc"})
        r = client.post(
            "/api/v1/game/add-point?oid=abc",
            json={"team": 1},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert body["state"]["team_1"]["scores"]["set_1"] == 1

    def test_add_set_updates_count(self, client, fake_backend_cls):
        client.post("/api/v1/session/init", json={"oid": "abc"})
        r = client.post(
            "/api/v1/game/add-set?oid=abc",
            json={"team": 1},
        )
        assert r.status_code == 200
        assert r.json()["state"]["team_1"]["sets"] == 1


# ---------------------------------------------------------------------------
# WebSocket /ws
# ---------------------------------------------------------------------------

class TestWebSocketRoute:
    def test_ws_rejects_unknown_oid(self, client):
        with pytest.raises(Exception):
            with client.websocket_connect("/api/v1/ws?oid=nobody"):
                pass  # connection should close with code 4004

    def test_ws_receives_initial_state(self, client, fake_backend_cls):
        client.post("/api/v1/session/init", json={"oid": "abc"})
        with client.websocket_connect("/api/v1/ws?oid=abc") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "state_update"
            assert msg["data"]["current_set"] == 1

    def test_ws_pong(self, client, fake_backend_cls):
        client.post("/api/v1/session/init", json={"oid": "abc"})
        with client.websocket_connect("/api/v1/ws?oid=abc") as ws:
            ws.receive_json()  # initial state_update
            ws.send_text("ping")
            assert ws.receive_text() == "pong"


# ---------------------------------------------------------------------------
# WSHub broadcast across multiple clients
# ---------------------------------------------------------------------------

class TestWSHubBroadcast:
    def test_broadcast_reaches_all_clients(self, client, fake_backend_cls):
        client.post("/api/v1/session/init", json={"oid": "abc"})

        with client.websocket_connect("/api/v1/ws?oid=abc") as ws1, \
                client.websocket_connect("/api/v1/ws?oid=abc") as ws2:
            ws1.receive_json()  # initial
            ws2.receive_json()  # initial

            # Trigger a state change via HTTP → handler broadcasts via WSHub.
            r = client.post(
                "/api/v1/game/add-point?oid=abc",
                json={"team": 1},
            )
            assert r.status_code == 200

            for ws in (ws1, ws2):
                msg = ws.receive_json()
                assert msg["type"] == "state_update"
                assert msg["data"]["team_1"]["scores"]["set_1"] == 1
