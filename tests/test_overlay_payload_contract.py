"""The overlay state contract (``app/overlay/payload_schema.py``).

The overlay templates' JavaScript reads one JSON document. These tests pin
that document to the published contract from both ends: what the builder
emits must validate (unknown keys fail), what the WebSocket sends must be the
public projection only, and the committed schema/type files must match the
models.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import action_log
from app.api.game_service import GameService
from app.api.session_manager import SessionManager
from app.conf import Conf
from app.customization import Customization
from app.overlay.payload_schema import (
    PUBLIC_KEYS,
    OverlayPayload,
    OverlayState,
    public_overlay_state,
)
from app.overlay_payload import build_overlay_payload
from app.state import State

ROOT = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.usefixtures("clean_sessions")


def _wire(document: dict) -> dict:
    """The document as a client receives it (JSON: map keys become strings)."""
    return json.loads(json.dumps(document))


def _payload(model, *, oid: str, rules: dict | None = None, **kwargs) -> dict:
    conf = Conf()
    conf.oid = oid
    return build_overlay_payload(
        model,
        dict(Customization.reset_state),
        conf=conf,
        rule_overrides_getter=(lambda: rules) if rules is not None else None,
        logger=logging.getLogger("test"),
        **kwargs,
    )


def _played_match(oid: str, mock_conf, api_backend) -> State:
    """Drive a real session so every audit-derived stats field is populated."""
    session = SessionManager.get_or_create(oid, mock_conf, api_backend)
    GameService.reset(session)
    for team in (1, 1, 2, 1, 2, 2, 2, 1):
        GameService.add_point(session, team=team, point_type="kill")
    GameService.add_point(session, team=2, point_type="opp_error", error_type="net_fault")
    GameService.add_timeout(session, team=1)
    GameService.change_serve(session, team=1)
    for _ in range(25):
        GameService.add_point(session, team=1, point_type="ace")
    assert session.current_set == 2
    return session.game_manager.get_current_state()


class TestBuilderMatchesContract:
    def test_blank_overlay(self):
        OverlayPayload.model_validate(_wire(_payload(State(), oid="blank")))

    @pytest.mark.parametrize("mode", ["indoor", "beach", "table_tennis"])
    def test_mid_match_with_every_optional_section(self, mode, mock_conf, api_backend):
        oid = f"contract-{mode}"
        state = _played_match(oid, mock_conf, api_backend)
        assert action_log.read_all(oid)
        payload = _payload(
            state,
            oid=oid,
            rules={
                "mode": mode,
                "auto_swap_sides": True,
                "set_summary": True,
                "match_started_at": 1.0,
            },
            show_only_current_set=True,
            force_visibility=False,
        )
        model = OverlayPayload.model_validate(_wire(payload))
        stats = model.overlay_control.stats
        assert stats is not None and stats.total_points > 0
        assert model.overlay_control.points_history
        if mode == "beach":
            assert model.overlay_control.beach_side_switch is not None

    def test_unknown_key_breaks_the_contract(self):
        """The point of ``extra="forbid"``: a new field must be declared."""
        payload = _payload(State(), oid="extra")
        payload["team_home"]["jersey_number"] = 7
        with pytest.raises(ValueError):
            OverlayPayload.model_validate(_wire(payload))


class TestPublicProjection:
    def test_bookkeeping_never_leaves_the_server(self):
        stored = {
            "_meta": {"overlay_id": "42:court-1"},
            "raw_remote_model": {"Team 1 Sets": "1"},
            "raw_remote_customization": {"locale": "es"},
            "match_info": {},
            "team_home": {},
            "team_away": {},
            "overlay_control": {},
        }
        out = public_overlay_state(stored)
        assert set(out) == PUBLIC_KEYS
        assert "_meta" not in out and "raw_remote_model" not in out

    def test_stored_state_projects_onto_the_contract(self, mock_conf, api_backend):
        from app.overlay import overlay_state_store

        oid = "contract-store"
        overlay_state_store.create_overlay(oid)
        state = _played_match(oid, mock_conf, api_backend)
        overlay_state_store.set_raw_config(oid, customization=dict(Customization.reset_state))
        overlay_state_store.update_state_sync(oid, _payload(state, oid=oid))
        OverlayState.model_validate(_wire(public_overlay_state(overlay_state_store.get_state(oid))))

    def test_websocket_sends_only_the_projection(self, auth_client):
        res = auth_client.post("/api/v1/session/init", json={"oid": "ws-proj"})
        assert res.status_code == 200
        overlay = next(
            o for o in auth_client.get("/api/v1/overlays").json() if o["oid"] == "ws-proj"
        )
        with TestClient(auth_client.app).websocket_connect(
            f"/ws/{overlay['public_token']}"
        ) as ws:
            first = ws.receive_json()
        assert "_meta" not in first and "raw_remote_model" not in first
        assert str(auth_client.test_user_id) not in str(first.get("_meta", ""))
        OverlayState.model_validate(first)


def test_committed_schema_files_are_current():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "generate_overlay_schema.py"), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        "overlay_static/schema is stale; run `python scripts/generate_overlay_schema.py` "
        "and `cd frontend && npm run gen:overlay-types`.\n" + result.stderr
    )


def test_generated_types_match_the_openapi_snapshot():
    """The .d.ts must come from the committed OpenAPI wrapper (CI regenerates it)."""
    dts = (ROOT / "overlay_static" / "js" / "types" / "overlay-state.d.ts").read_text()
    for name in OverlayState.model_json_schema()["$defs"]:
        assert f"{name}:" in dts, f"{name} missing from overlay-state.d.ts — regenerate it"


def test_server_time_is_stamped_at_send_time(monkeypatch):
    """A reconnecting client must not derive its clock skew from the
    server_time of a broadcast that happened hours ago."""
    from app.overlay import payload_schema

    monkeypatch.setattr(payload_schema.time, "time", lambda: 1_800_000_000.0)
    stored = {"match_info": {"server_time": 1_700_000_000.0, "current_set": 1}}
    out = public_overlay_state(stored)
    assert out["match_info"]["server_time"] == 1_800_000_000.0
    assert stored["match_info"]["server_time"] == 1_700_000_000.0  # not mutated


def test_stale_beach_countdown_is_not_sent_outside_beach_mode():
    """State stored by an older release can still hold a beach countdown
    after the rules changed to indoor; the feed must not show it."""
    countdown = {"interval": 7, "points_in_set": 2, "next_switch_at": 7,
                 "points_until_switch": 5, "is_switch_pending": False}
    stored = {
        "match_info": {"mode": "indoor", "current_set": 1},
        "overlay_control": {"beach_side_switch": countdown},
    }
    out = public_overlay_state(stored)
    assert out["overlay_control"]["beach_side_switch"] is None
    assert stored["overlay_control"]["beach_side_switch"] == countdown  # not mutated

    stored["match_info"]["mode"] = "beach"
    assert public_overlay_state(stored)["overlay_control"]["beach_side_switch"] == countdown
