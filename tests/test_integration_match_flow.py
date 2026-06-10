"""End-to-end match lifecycle through a real ``create_app()`` instance.

Drives the full chain the unit suite only covers in isolation:

    session init → rules → start-match → points (incl. timeout + undo)
    → set end → match end → webhook delivery → match archive
    → /api/v1/matches listing → /match/{id}/report HTML
    → overlay store final state (GameManager → Backend → LocalOverlayBackend)

Uses the ``test_overlay`` custom overlay seeded by the autouse
``isolate_overlay_store`` fixture, so the whole flow stays in-process —
no overlays.uno HTTP. Webhook network I/O is captured by patching
``requests.post``; the SSRF guard passes the example host through because
DNS failures are deliberately non-blocking (see ``_is_target_safe``).
"""

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.api import webhooks
from app.api.webhooks import WebhookDispatcher
from app.bootstrap import create_app

pytestmark = pytest.mark.usefixtures("clean_sessions")

OID = "test_overlay"
WEBHOOK_URL = "https://hooks.example.com/volley"
WEBHOOK_SECRET = "e2e-secret"

# Fast format so the full match is ~20 HTTP calls: best of 3, sets to 3
# points (last set too), win by 2.
POINTS = 3
SETS = 3


@pytest.fixture
def webhook_env(monkeypatch):
    monkeypatch.setenv("WEBHOOKS_URL", WEBHOOK_URL)
    monkeypatch.setenv("WEBHOOKS_SECRET", WEBHOOK_SECRET)
    monkeypatch.setenv("WEBHOOKS_EVENTS", "set_end,match_end")
    monkeypatch.setenv("MATCH_REPORT_PUBLIC", "true")
    monkeypatch.delenv("SCOREBOARD_USERS", raising=False)


@pytest.fixture
def dispatcher(monkeypatch, webhook_env):
    """Fresh dispatcher wired into the game hooks for this test only."""
    d = WebhookDispatcher()
    monkeypatch.setattr(webhooks, "webhook_dispatcher", d)
    monkeypatch.setattr("app.api.game_audit_hooks.webhook_dispatcher", d)
    yield d
    d.shutdown()


@pytest.fixture
def client():
    with TestClient(create_app()) as c:
        yield c


def _drain(dispatcher):
    """Wait for queued webhook deliveries before asserting on them."""
    if dispatcher._executor is not None:
        dispatcher._executor.shutdown(wait=True)
        dispatcher._executor = None


def _win_set(client, team: int, points: int = POINTS):
    for _ in range(points):
        r = client.post(f"/api/v1/game/add-point?oid={OID}", json={"team": team})
        assert r.status_code == 200, r.text


def test_full_match_lifecycle(client, dispatcher):
    with patch("app.api.webhooks.requests.post") as post:
        post.return_value.status_code = 200

        # --- session bootstrap -------------------------------------------
        r = client.post("/api/v1/session/init", json={"oid": OID})
        assert r.status_code == 200, r.text
        assert r.json()["success"] is True

        r = client.post(
            f"/api/v1/session/rules?oid={OID}",
            json={
                "points_limit": POINTS,
                "points_limit_last_set": POINTS,
                "sets_limit": SETS,
            },
        )
        assert r.status_code == 200, r.text

        r = client.post(f"/api/v1/game/start-match?oid={OID}")
        assert r.status_code == 200, r.text

        # --- play: team 1 wins 2-1 ---------------------------------------
        # Set 1 with a timeout and an undone stray point for team 2.
        r = client.post(f"/api/v1/game/add-timeout?oid={OID}", json={"team": 2})
        assert r.status_code == 200, r.text
        r = client.post(f"/api/v1/game/add-point?oid={OID}", json={"team": 2})
        assert r.status_code == 200, r.text
        r = client.post(f"/api/v1/game/undo?oid={OID}")
        assert r.status_code == 200, r.text

        _win_set(client, team=1)   # set 1 → 1-0
        _win_set(client, team=2)   # set 2 → 1-1
        _win_set(client, team=1)   # set 3 → 2-1, match over

        r = client.get(f"/api/v1/state?oid={OID}")
        assert r.status_code == 200
        state = r.json()
        assert state["team_1"]["sets"] == 2
        assert state["team_2"]["sets"] == 1
        assert state["match_finished"] is True

        # --- webhooks ------------------------------------------------------
        _drain(dispatcher)
        bodies = []
        for call in post.call_args_list:
            body = json.loads(call.kwargs["data"])
            bodies.append(body)
            assert body["oid"] == OID
            sig = call.kwargs["headers"]["X-Webhook-Signature"]
            assert sig.startswith("sha256=")
        events = [b["event"] for b in bodies]
        assert events.count("set_end") == 3
        assert events.count("match_end") == 1
        # Deliveries fan out across the dispatcher's worker threads, so
        # call order is not guaranteed — locate match_end by event, not
        # by position.
        match_end_body = next(b for b in bodies if b["event"] == "match_end")
        assert match_end_body["state"]["match_finished"] is True

        # --- archive -------------------------------------------------------
        r = client.get(f"/api/v1/matches?oid={OID}")
        assert r.status_code == 200
        listing = r.json()
        assert listing["count"] == 1
        summary = listing["matches"][0]
        assert summary["oid"] == OID
        assert summary["winning_team"] == 1
        match_id = summary["match_id"]

        r = client.get(f"/api/v1/matches/{match_id}")
        assert r.status_code == 200
        snapshot = r.json()
        assert snapshot["final_state"]["team_1"]["sets"] == 2
        audit_actions = [rec["action"] for rec in snapshot["audit_log"]]
        assert "add_point" in audit_actions
        assert "add_timeout" in audit_actions

        # --- report --------------------------------------------------------
        r = client.get(f"/match/{match_id}/report")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]

        # --- overlay store (in-process LocalOverlayBackend) ----------------
        from app.overlay import overlay_state_store

        overlay_state = overlay_state_store.get_state(OID)
        assert overlay_state is not None
        home_sets = overlay_state["team_home"]["sets_won"]
        away_sets = overlay_state["team_away"]["sets_won"]
        assert sorted([home_sets, away_sets]) == [1, 2]


def test_undo_does_not_fire_webhooks(client, dispatcher):
    """Undoing a point must not emit set_end/match_end events."""
    with patch("app.api.webhooks.requests.post") as post:
        post.return_value.status_code = 200

        client.post("/api/v1/session/init", json={"oid": OID})
        client.post(
            f"/api/v1/session/rules?oid={OID}",
            json={
                "points_limit": POINTS,
                "points_limit_last_set": POINTS,
                "sets_limit": SETS,
            },
        )
        client.post(f"/api/v1/game/add-point?oid={OID}", json={"team": 1})
        client.post(f"/api/v1/game/undo?oid={OID}")

        _drain(dispatcher)
        assert post.call_args_list == []
