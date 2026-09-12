"""Tests for ``app.overlay_payload`` — the overlay/spectator wire payload."""

import logging

from app.conf import Conf
from app.customization import Customization
from app.overlay_payload import build_overlay_payload
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
