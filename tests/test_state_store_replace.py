"""Tests for the audit-derived subtree replacement in OverlayStateStore.

When :func:`GameService.reset` clears the per-OID audit log, the next
broadcast carries empty ``points_by_set`` / ``timeouts_by_set`` /
``stats.set_durations`` dicts. Without explicit replacement the
state-store deep-merge would leave per-set entries from the previous
match in place, so the spectator (follow) page would keep rendering
stale stats / time history after the operator hit Reset.
"""

import pytest

# Imports must go through ``app.api`` first to avoid the partial-init
# cycle: importing :mod:`app.overlay.state_store` directly triggers
# :mod:`app.overlay.__init__` which re-imports this module, while
# :mod:`app.api.routes` already wired up the resolution order in the
# rest of the test suite.
from app.api import action_log  # noqa: F401  (load order)
from app.overlay.state_store import OverlayStateStore


@pytest.fixture
def store(tmp_path):
    return OverlayStateStore(
        data_dir=str(tmp_path / "data"),
        templates_dir=str(tmp_path / "tpl"),
    )


def _seed_with_per_set_stats(store, oid):
    """Drop a payload representing a multi-set match in progress."""
    store.update_state_sync(oid, {
        "overlay_control": {
            "points_by_set": {
                "1": [{"team": 1, "ts": 1.0, "score": [1, 0]}],
                "2": [{"team": 2, "ts": 5.0, "score": [0, 1]}],
            },
            "timeouts_by_set": {
                "1": [{"team": 1, "ts": 2.0}],
            },
            "stats": {
                "set_durations": {"1": 90.0, "2": 60.0},
                "services": {"1": {"served": 5, "won": 3}},
                "points_history": [{"team": 1, "ts": 1.0, "score": [1, 0]}],
            },
        },
    })


def test_reset_clears_per_set_buckets(store):
    """Empty per-set dicts in a fresh broadcast must wipe stale keys.

    The pre-fix deep_merge behaviour would treat ``{}`` as a no-op
    against the existing dict and leave ``set_1``/``set_2`` in place,
    which is exactly the bug the spectator page surfaces (stats and
    time-history stuck at the previous match's values after Reset).
    """
    oid = "reset-buckets"
    assert store.create_overlay(oid) is True
    _seed_with_per_set_stats(store, oid)
    seeded = store.get_state(oid)
    assert seeded["overlay_control"]["points_by_set"] != {}
    assert seeded["overlay_control"]["timeouts_by_set"] != {}
    assert seeded["overlay_control"]["stats"]["set_durations"] != {}

    # Simulate the broadcast that follows GameService.reset (audit log
    # is empty, so every audit-derived bucket is empty).
    store.update_state_sync(oid, {
        "overlay_control": {
            "points_by_set": {},
            "timeouts_by_set": {},
            "stats": {
                "set_durations": {},
                "services": {
                    "1": {"served": 0, "won": 0},
                    "2": {"served": 0, "won": 0},
                },
                "points_history": [],
            },
        },
    })
    cleared = store.get_state(oid)
    assert cleared["overlay_control"]["points_by_set"] == {}
    assert cleared["overlay_control"]["timeouts_by_set"] == {}
    assert cleared["overlay_control"]["stats"]["set_durations"] == {}
    # Services is replaced wholesale too — both teams reset to 0/0.
    assert cleared["overlay_control"]["stats"]["services"] == {
        "1": {"served": 0, "won": 0},
        "2": {"served": 0, "won": 0},
    }


def test_partial_payload_does_not_touch_unrelated_subtrees(store):
    """Theme / admin updates that only carry colours must not blow
    away the audit-derived subtrees."""
    oid = "partial"
    assert store.create_overlay(oid) is True
    _seed_with_per_set_stats(store, oid)
    store.update_state_sync(oid, {
        "overlay_control": {
            "colors": {"set_bg": "#000"},
        },
    })
    state = store.get_state(oid)
    assert state["overlay_control"]["points_by_set"] != {}
    assert state["overlay_control"]["stats"]["set_durations"] != {}
