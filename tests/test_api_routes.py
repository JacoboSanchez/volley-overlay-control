"""Integration tests for app/api/routes/* using FastAPI's TestClient.

Covers the HTTP and WebSocket surface end-to-end: session lifecycle, game
actions, session-not-found errors, and WSHub broadcast across multiple
clients. Backend HTTP dependencies are patched so no network traffic occurs.
"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

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

    def test_start_match_arms_timer(self, client, fake_backend_cls):
        client.post("/api/v1/session/init", json={"oid": "abc"})
        # Fresh session: timer starts unarmed.
        r = client.post("/api/v1/game/start-match?oid=abc")
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        anchor = body["state"]["match_started_at"]
        assert isinstance(anchor, (int, float)) and anchor > 0
        # Idempotent: second call leaves the original anchor in place.
        r2 = client.post("/api/v1/game/start-match?oid=abc")
        assert r2.json()["state"]["match_started_at"] == anchor

    def test_add_set_updates_count(self, client, fake_backend_cls):
        client.post("/api/v1/session/init", json={"oid": "abc"})
        r = client.post(
            "/api/v1/game/add-set?oid=abc",
            json={"team": 1},
        )
        assert r.status_code == 200
        assert r.json()["state"]["team_1"]["sets"] == 1

    def test_add_point_accepts_control_alias(self, client, fake_backend_cls):
        client.post("/api/v1/session/init", json={"oid": "abc"})
        r = client.post(
            "/api/v1/game/add-point?control=abc",
            json={"team": 1},
        )
        assert r.status_code == 200
        assert r.json()["state"]["team_1"]["scores"]["set_1"] == 1

    def test_missing_oid_and_control_returns_422(self, client, fake_backend_cls):
        client.post("/api/v1/session/init", json={"oid": "abc"})
        r = client.post("/api/v1/game/add-point", json={"team": 1})
        assert r.status_code == 422


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

    def test_ws_accepts_control_alias(self, client, fake_backend_cls):
        client.post("/api/v1/session/init", json={"oid": "abc"})
        with client.websocket_connect("/api/v1/ws?control=abc") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "state_update"
            assert msg["data"]["current_set"] == 1


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


class TestWSHubResilience:
    def test_broadcast_evicts_failing_socket(self):
        """A send that raises is treated as stale and removed from the hub."""
        import asyncio as _asyncio
        from unittest.mock import AsyncMock

        from app.api.ws_hub import WSHub

        WSHub.clear()
        healthy = AsyncMock()
        broken = AsyncMock()
        broken.send_text.side_effect = RuntimeError("peer gone")
        WSHub._connections["oid1"] = {healthy, broken}

        _asyncio.run(WSHub.broadcast("oid1", {"current_set": 1}))

        assert broken not in WSHub._connections.get("oid1", set())
        assert healthy in WSHub._connections.get("oid1", set())
        WSHub.clear()

    def test_broadcast_preserves_reconnected_oid(self):
        """If a new client installs a fresh set under the same OID while
        broadcast was awaiting, the final cleanup must not pop that new set."""
        import asyncio as _asyncio
        from unittest.mock import AsyncMock

        from app.api.ws_hub import WSHub

        WSHub.clear()
        old_ws = AsyncMock()
        old_ws.send_text.side_effect = RuntimeError("peer gone")
        old_set = {old_ws}
        WSHub._connections["oid1"] = old_set

        async def _run():
            # Start broadcast; the failing send will empty ``old_set``.
            task = _asyncio.create_task(
                WSHub.broadcast("oid1", {"current_set": 1}),
            )
            # Simulate a concurrent disconnect+reconnect: the old set is
            # replaced in the registry by a brand-new set with a new client.
            await _asyncio.sleep(0)
            new_ws = AsyncMock()
            WSHub._connections["oid1"] = {new_ws}
            await task
            return new_ws

        new_ws = _asyncio.run(_run())

        # The newly-connected client must still be in the registry — the
        # cleanup should only pop the OID if the same set instance is still
        # there.
        assert "oid1" in WSHub._connections
        assert new_ws in WSHub._connections["oid1"]
        WSHub.clear()

    def test_broadcast_times_out_slow_socket(self, monkeypatch):
        """A socket that never finishes send is dropped via the timeout."""
        import asyncio as _asyncio
        from unittest.mock import AsyncMock

        from app.api.ws_hub import WSHub

        # Shrink the timeout so the test is quick.
        monkeypatch.setattr(WSHub, "_BROADCAST_SEND_TIMEOUT", 0.05)
        WSHub.clear()

        async def _never(_msg):
            await _asyncio.sleep(1.0)

        slow = AsyncMock()
        slow.send_text.side_effect = _never
        WSHub._connections["oid1"] = {slow}

        _asyncio.run(WSHub.broadcast("oid1", {"current_set": 1}))

        assert "oid1" not in WSHub._connections
        WSHub.clear()
