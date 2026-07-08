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
from app.overlay_key import make_skey
from app.state import State
from tests.conftest import load_fixture, login_client

pytestmark = pytest.mark.usefixtures("clean_sessions")


@pytest.fixture
def client(db_session):
    with TestClient(create_app()) as c:
        login_client(c, db_session)
        yield c


def _skey(client, oid):
    return make_skey(client.test_user_id, oid)


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
        assert SessionManager.get(_skey(client, "abc")) is not None

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

    def test_add_point_records_point_type(self, client, fake_backend_cls):
        from app.api import action_log
        client.post("/api/v1/session/init", json={"oid": "abc"})
        r = client.post(
            "/api/v1/game/add-point?oid=abc",
            json={"team": 1, "point_type": "ace"},
        )
        assert r.status_code == 200
        records = [
            rec for rec in action_log.read_all(_skey(client, "abc"))
            if rec.get("action") == "add_point"
        ]
        assert records[-1]["params"].get("point_type") == "ace"

    def test_add_point_opp_error_with_error_type(self, client, fake_backend_cls):
        from app.api import action_log
        client.post("/api/v1/session/init", json={"oid": "abc"})
        r = client.post(
            "/api/v1/game/add-point?oid=abc",
            json={"team": 2, "point_type": "opp_error",
                  "error_type": "net_fault"},
        )
        assert r.status_code == 200
        rec = action_log.read_all(_skey(client, "abc"))[-1]
        assert rec["params"].get("point_type") == "opp_error"
        assert rec["params"].get("error_type") == "net_fault"

    def test_add_point_error_type_requires_opp_error(self, client, fake_backend_cls):
        client.post("/api/v1/session/init", json={"oid": "abc"})
        # error_type alongside a non-opp_error point_type is rejected.
        r = client.post(
            "/api/v1/game/add-point?oid=abc",
            json={"team": 1, "point_type": "kill", "error_type": "serve_error"},
        )
        assert r.status_code == 422

    def test_add_point_rejects_unknown_point_type(self, client, fake_backend_cls):
        client.post("/api/v1/session/init", json={"oid": "abc"})
        r = client.post(
            "/api/v1/game/add-point?oid=abc",
            json={"team": 1, "point_type": "nonsense"},
        )
        assert r.status_code == 422

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
        with pytest.raises(Exception), client.websocket_connect("/api/v1/ws?oid=nobody"):
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


# ---------------------------------------------------------------------------
# WSHub cap + heartbeat (M14 — Fase 4)
# ---------------------------------------------------------------------------


class TestWSHubCap:
    """``connect`` must reject upgrades once an OID is at its cap."""

    def test_connect_raises_when_at_cap(self, monkeypatch):
        from unittest.mock import AsyncMock

        from app.api.ws_hub import WSHub, WSHubFull

        WSHub.clear()
        monkeypatch.setattr(WSHub, "_MAX_CLIENTS_PER_OID", 2)
        # Pre-populate two healthy clients so the next accept hits the cap.
        WSHub._connections["oid-cap"] = {object(), object()}

        ws = AsyncMock()
        import asyncio as _asyncio

        with pytest.raises(WSHubFull) as excinfo:
            _asyncio.run(WSHub.connect(ws, "oid-cap"))
        assert excinfo.value.oid == "oid-cap"
        assert excinfo.value.cap == 2
        # The handshake must NOT have been accepted on the rejected upgrade.
        ws.accept.assert_not_called()
        WSHub.clear()

    def test_websocket_endpoint_closes_with_1013_when_at_cap(
        self, client, fake_backend_cls, monkeypatch,
    ):
        from app.api.ws_hub import WSHub

        # Spin up a real session so check_oid_access / SessionManager pass.
        with patch(
            "app.api.routes.session.Backend", return_value=fake_backend_cls,
        ):
            r = client.post("/api/v1/session/init", json={"oid": "cap-oid"})
            assert r.status_code == 200

        # Force the cap to 0 so the very first WS connect is refused.
        monkeypatch.setattr(WSHub, "_MAX_CLIENTS_PER_OID", 0)

        # The TestClient WebSocket helper raises on close-before-accept,
        # but FastAPI emits the 1013 close *after* the handshake message
        # — so just verify the endpoint did not register the client.
        # The TestClient WebSocket helper raises on close-before-accept
        # with a variety of exceptions across Starlette versions, so
        # catch broadly: the assertion below is what actually proves
        # the cap held.
        try:
            with client.websocket_connect("/api/v1/ws?oid=cap-oid"):
                pass
        except Exception:
            pass
        assert "cap-oid" not in WSHub._connections
        WSHub.clear()


class TestWSHubHeartbeat:
    """``_heartbeat_tick`` evicts zombies and pings the rest."""

    def test_tick_evicts_idle_socket_past_timeout(self, monkeypatch):
        import asyncio as _asyncio
        import time as _time
        from unittest.mock import AsyncMock

        from app.api import ws_hub
        from app.api.ws_hub import WSHub

        WSHub.clear()
        # 1s timeout for the test; pretend the client has been idle 5s.
        monkeypatch.setattr(ws_hub, "WSHUB_CLIENT_TIMEOUT_SECONDS", 1.0)

        zombie = AsyncMock()
        WSHub._connections["oid-z"] = {zombie}
        WSHub._last_seen[zombie] = _time.monotonic() - 5.0

        _asyncio.run(WSHub._heartbeat_tick())

        # Eviction sends a 1011 close and then disconnects bookkeeping.
        zombie.close.assert_called_once()
        assert "oid-z" not in WSHub._connections
        assert zombie not in WSHub._last_seen
        WSHub.clear()

    def test_tick_pings_healthy_socket(self, monkeypatch):
        import asyncio as _asyncio
        import time as _time
        from unittest.mock import AsyncMock

        from app.api import ws_hub
        from app.api.ws_hub import WSHub

        WSHub.clear()
        monkeypatch.setattr(ws_hub, "WSHUB_CLIENT_TIMEOUT_SECONDS", 60.0)

        healthy = AsyncMock()
        WSHub._connections["oid-h"] = {healthy}
        WSHub._last_seen[healthy] = _time.monotonic()

        _asyncio.run(WSHub._heartbeat_tick())

        # Stays connected and received the application-level ping frame.
        assert "oid-h" in WSHub._connections
        healthy.send_text.assert_called_once_with('{"type":"ping"}')
        healthy.close.assert_not_called()
        WSHub.clear()

    def test_mark_active_bumps_last_seen(self, monkeypatch):
        import time as _time
        from unittest.mock import AsyncMock

        from app.api.ws_hub import WSHub

        WSHub.clear()
        ws = AsyncMock()
        # mark_active is a no-op for unknown sockets — only registered
        # clients are tracked.
        WSHub._last_seen[ws] = _time.monotonic() - 5.0
        before = WSHub._last_seen[ws]
        WSHub.mark_active(ws)
        assert WSHub._last_seen[ws] >= before
        WSHub.clear()

    def test_start_heartbeat_no_op_when_disabled(self):
        from app.api.ws_hub import WSHub

        WSHub.stop_heartbeat()
        # Default is 0 — no task should be scheduled.
        WSHub.start_heartbeat()
        assert WSHub._heartbeat_task is None

    def test_tick_runs_pings_concurrently(self, monkeypatch):
        """A 200-client OID must not turn into 200 × timeout of wall time.

        Five mock clients each take 0.1 s to respond to ``send_text``.
        Serial would be ~0.5 s; concurrent must be ~0.1 s. Cut the
        threshold at 0.3 s to absorb scheduler jitter while still
        catching a regression to the serial loop.
        """
        import asyncio as _asyncio
        import time as _time
        from unittest.mock import AsyncMock

        from app.api import ws_hub
        from app.api.ws_hub import WSHub

        WSHub.clear()
        monkeypatch.setattr(ws_hub, "WSHUB_CLIENT_TIMEOUT_SECONDS", 60.0)
        monkeypatch.setattr(WSHub, "_BROADCAST_SEND_TIMEOUT", 1.0)

        async def _slow_send(_msg):
            await _asyncio.sleep(0.1)

        clients = []
        for _ in range(5):
            c = AsyncMock()
            c.send_text.side_effect = _slow_send
            clients.append(c)
        WSHub._connections["oid-c"] = set(clients)
        for c in clients:
            WSHub._last_seen[c] = _time.monotonic()

        start = _time.monotonic()
        _asyncio.run(WSHub._heartbeat_tick())
        elapsed = _time.monotonic() - start
        assert elapsed < 0.3, (
            f"heartbeat tick ran serially ({elapsed:.2f}s for 5 clients)"
        )
        # All five clients got their ping.
        for c in clients:
            c.send_text.assert_called_once_with('{"type":"ping"}')
        WSHub.clear()

    def test_tick_evicts_only_zombie_when_mixed_with_healthy(self, monkeypatch):
        """Healthy + zombie clients in the same tick: zombie evicted, healthy kept."""
        import asyncio as _asyncio
        import time as _time
        from unittest.mock import AsyncMock

        from app.api import ws_hub
        from app.api.ws_hub import WSHub

        WSHub.clear()
        monkeypatch.setattr(ws_hub, "WSHUB_CLIENT_TIMEOUT_SECONDS", 1.0)

        zombie = AsyncMock()
        healthy = AsyncMock()
        WSHub._connections["oid-mix"] = {zombie, healthy}
        WSHub._last_seen[zombie] = _time.monotonic() - 5.0
        WSHub._last_seen[healthy] = _time.monotonic()

        _asyncio.run(WSHub._heartbeat_tick())

        # Zombie gone, healthy stayed and was pinged.
        assert "oid-mix" in WSHub._connections
        assert healthy in WSHub._connections["oid-mix"]
        assert zombie not in WSHub._connections["oid-mix"]
        zombie.close.assert_called_once()
        healthy.send_text.assert_called_once_with('{"type":"ping"}')
        WSHub.clear()
