"""Tests for ``app.overlay_payload`` — the overlay/spectator wire payload."""

import logging

from app.conf import Conf
from app.customization import Customization
from app.overlay_payload import _add_live_stats, build_overlay_payload
from app.state import State


def _build(model: dict) -> dict:
    return build_overlay_payload(
        model,
        dict(Customization.reset_state),
        conf=Conf(),
        rule_overrides_getter=None,
        logger=logging.getLogger("test"),
    )


def test_team_payload_exposes_persisted_per_set_timeouts():
    """The recap reads per-set totals from the payload, not the audit log.

    The audit append is best-effort, so the payload must carry the
    authoritative per-set counters the cap is enforced against.
    """
    model = {
        State.CURRENT_SET_INT: 2,
        State._t_timeouts_key(1, 1): "2",
        State._t_timeouts_key(1, 2): "1",
        State._t_timeouts_key(2, 1): "1",
    }
    payload = _build(model)

    assert payload["team_home"]["timeouts_by_set"]["set_1"] == 2
    assert payload["team_home"]["timeouts_by_set"]["set_2"] == 1
    assert payload["team_away"]["timeouts_by_set"]["set_1"] == 1
    assert payload["team_away"]["timeouts_by_set"]["set_2"] == 0


def test_persisted_timeouts_default_to_zero_when_absent():
    payload = _build({State.CURRENT_SET_INT: 1})
    assert payload["team_home"]["timeouts_by_set"]["set_1"] == 0
    assert payload["team_away"]["timeouts_by_set"]["set_1"] == 0


def test_legacy_flat_timeout_migrates_into_current_set():
    """A pre-per-set model (flat counter only) must not recap as zero."""
    model = {
        State.CURRENT_SET_INT: 2,
        State.T1TIMEOUTS_INT: "1",
    }
    payload = _build(model)
    assert payload["team_home"]["timeouts_by_set"]["set_2"] == 1
    assert payload["team_home"]["timeouts_by_set"]["set_1"] == 0


def _fake_live_stats(points_by_set: dict[int, list[dict]]) -> dict:
    return {
        "current_streak": {},
        "longest_streak": {},
        "partial_comeback": {},
        "set_win_comeback": {},
        "total_points": 0,
        "set_durations": {},
        "services": {},
        "longest_streak_by_set": {},
        "services_by_set": {},
        "point_types": {},
        "error_types": {},
        "point_types_by_set": {},
        "last_point": None,
        "points_history": [],
        "points_by_set": points_by_set,
        "timeouts_by_set": {},
    }


def test_rallies_recap_uncaps_only_the_displayed_set(monkeypatch):
    from app.api import live_stats

    calls = []
    capped = {1: [{"action": "add_point"}] * 60}
    complete = {1: [{"action": "add_point"}] * 62}

    def fake_compute(_oid, **kwargs):
        calls.append(kwargs)
        return _fake_live_stats(
            complete
            if kwargs.get("points_by_set_uncapped_set") == 1
            else capped
        )

    monkeypatch.setattr(live_stats, "compute_live_stats", fake_compute)
    payload = {
        "match_info": {
            "current_set": 2,
            "show_set_summary": True,
            "set_summary_style": "brand_ledger",
        },
        "overlay_control": {},
    }
    _add_live_stats(payload, "user:overlay", logging.getLogger("test"))

    assert calls == [
        {"history_limit": 30},
        {"history_limit": 30, "points_by_set_uncapped_set": 1},
    ]
    assert len(payload["overlay_control"]["points_by_set"]["1"]) == 62
    assert payload["match_info"]["summary_set_num"] == 1


def test_hidden_rallies_recap_keeps_the_transport_cap(monkeypatch):
    from app.api import live_stats

    calls = []

    def fake_compute(_oid, **kwargs):
        calls.append(kwargs)
        return _fake_live_stats({1: [{"action": "add_point"}] * 60})

    monkeypatch.setattr(live_stats, "compute_live_stats", fake_compute)
    payload = {
        "match_info": {
            "current_set": 2,
            "show_set_summary": False,
            "set_summary_style": "brand_ledger",
        },
        "overlay_control": {},
    }
    _add_live_stats(payload, "user:overlay", logging.getLogger("test"))

    assert calls == [{"history_limit": 30}]
    assert len(payload["overlay_control"]["points_by_set"]["1"]) == 60
