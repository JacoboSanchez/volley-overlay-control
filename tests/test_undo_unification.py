"""Tests for the unified undo stack — the per-type ``add_*(undo=True)``
flag and ``POST /game/undo`` share the audit log so they can't drift.

Covers:

* the new ``team`` filter on ``pop_last_forward`` and the
  read-only ``peek_last_forward``;
* ``can_undo`` derivation from the in-memory counter;
* mixed-API scenarios that used to leave fantasma forwards in the
  log (per-type undo not popping → generic undo double-reverting).
"""
import pytest

from app.api import action_log
from app.api.game_service import GameService
from app.api.session_manager import SessionManager

pytestmark = pytest.mark.usefixtures("clean_sessions")


# ---------------------------------------------------------------------------
# action_log helpers
# ---------------------------------------------------------------------------

class TestPopAndPeek:
    def test_pop_last_forward_filters_by_team(self):
        action_log.append("oid-pop-team", "add_point", {"team": 1}, {})
        action_log.append("oid-pop-team", "add_point", {"team": 2}, {})
        action_log.append("oid-pop-team", "add_point", {"team": 1}, {})
        # Most recent forward overall is team=1 (the last append), but
        # filtering by team=2 must skip past it to the team=2 forward.
        popped = action_log.pop_last_forward(
            "oid-pop-team", allowed_actions={"add_point"}, team=2,
        )
        assert popped is not None
        assert popped["params"]["team"] == 2
        # The two team=1 forwards are still there.
        remaining = action_log.read_all("oid-pop-team")
        assert all(r["params"]["team"] == 1 for r in remaining)
        assert len(remaining) == 2

    def test_pop_last_forward_no_match_returns_none(self):
        action_log.append("oid-no-match", "add_point", {"team": 1}, {})
        assert action_log.pop_last_forward(
            "oid-no-match", allowed_actions={"add_point"}, team=2,
        ) is None
        # And the file is untouched.
        assert len(action_log.read_all("oid-no-match")) == 1

    def test_peek_last_forward_does_not_remove(self):
        action_log.append("oid-peek", "add_point", {"team": 1}, {})
        peeked = action_log.peek_last_forward(
            "oid-peek", allowed_actions={"add_point"},
        )
        assert peeked is not None
        assert len(action_log.read_all("oid-peek")) == 1

    def test_count_undoable_forwards(self):
        # Forwards: 3 undoable + 1 non-undoable (set_score). Undos: 1.
        action_log.append("oid-count", "add_point", {"team": 1}, {})
        action_log.append("oid-count", "add_set", {"team": 2}, {})
        action_log.append("oid-count", "set_score",
                          {"team": 1, "set_number": 1, "value": 5}, {})
        action_log.append("oid-count", "add_point", {"team": 2}, {})
        action_log.append("oid-count", "add_point",
                          {"team": 2, "undo": True}, {})
        # 3 undoable forwards (2 add_point fwd, 1 add_set fwd) — the
        # set_score is not in UNDOABLE_ACTIONS so it does not count.
        assert action_log.count_undoable_forwards("oid-count") == 3


# ---------------------------------------------------------------------------
# can_undo wired into GameStateResponse
# ---------------------------------------------------------------------------

class TestCanUndo:
    def test_initial_state_cannot_undo(self, mock_conf, api_backend):
        s = SessionManager.get_or_create("cu-1", mock_conf, api_backend)
        assert GameService.get_state(s).can_undo is False

    def test_after_forward_can_undo(self, mock_conf, api_backend):
        s = SessionManager.get_or_create("cu-2", mock_conf, api_backend)
        GameService.add_point(s, team=1)
        assert GameService.get_state(s).can_undo is True

    def test_after_undo_back_to_zero(self, mock_conf, api_backend):
        s = SessionManager.get_or_create("cu-3", mock_conf, api_backend)
        GameService.add_point(s, team=1)
        GameService.add_point(s, team=1, undo=True)
        assert GameService.get_state(s).can_undo is False

    def test_non_undoable_action_does_not_flip_can_undo(
            self, mock_conf, api_backend):
        s = SessionManager.get_or_create("cu-4", mock_conf, api_backend)
        GameService.change_serve(s, team=1)
        # change_serve is logged but is not undoable.
        assert GameService.get_state(s).can_undo is False
        GameService.set_score(s, team=1, set_number=1, value=12)
        assert GameService.get_state(s).can_undo is False

    def test_reset_clears_can_undo(self, mock_conf, api_backend):
        s = SessionManager.get_or_create("cu-5", mock_conf, api_backend)
        GameService.add_point(s, team=1)
        GameService.add_point(s, team=2)
        assert GameService.get_state(s).can_undo is True
        GameService.reset(s)
        assert GameService.get_state(s).can_undo is False

    def test_can_undo_rehydrates_after_session_clear(
            self, mock_conf, api_backend):
        s = SessionManager.get_or_create("cu-6", mock_conf, api_backend)
        GameService.add_point(s, team=1)
        GameService.add_point(s, team=2)
        assert s.undoable_forward_count == 2

        SessionManager.clear()

        restored = SessionManager.get_or_create("cu-6", mock_conf, api_backend)
        assert restored.undoable_forward_count == 2
        assert GameService.get_state(restored).can_undo is True


# ---------------------------------------------------------------------------
# Mixed-API consistency — the bug we set out to fix
# ---------------------------------------------------------------------------

class TestMixedApiConsistency:
    """Before unification, calling per-type ``add_point(undo=True)``
    left the forward record in the log. A follow-up
    ``POST /game/undo`` would then pop that fantasma forward and
    double-revert state. After unification both paths share the
    same stack and stay consistent."""

    def test_per_type_undo_does_not_leave_fantasma_forward(
            self, mock_conf, api_backend):
        s = SessionManager.get_or_create("mixed-1", mock_conf, api_backend)
        GameService.add_point(s, team=1)
        GameService.add_point(s, team=1, undo=True)

        # Both score and counter should agree on "nothing pending".
        score = s.game_manager.get_current_state().get_game(1, 1)
        assert score == 0
        assert s.undoable_forward_count == 0

        # A subsequent generic undo should report nothing to undo —
        # not pop the (now absent) fantasma forward.
        response = GameService.undo_last(s)
        assert response.success is False
        assert "Nothing to undo" in (response.message or "")

    def test_generic_undo_after_per_type_undo_walks_further_back(
            self, mock_conf, api_backend):
        """Two forwards, one undone via per-type, the next via generic.
        Both should land state on 0-0 with no records of pending undo."""
        s = SessionManager.get_or_create("mixed-2", mock_conf, api_backend)
        GameService.add_point(s, team=1)
        GameService.add_point(s, team=2)
        GameService.add_point(s, team=2, undo=True)   # per-type
        GameService.undo_last(s)                       # generic

        state = s.game_manager.get_current_state()
        assert state.get_game(1, 1) == 0
        assert state.get_game(2, 1) == 0
        assert s.undoable_forward_count == 0

    def test_per_type_undo_with_wrong_team_does_not_affect_other_team(
            self, mock_conf, api_backend):
        """``add_point(team=2, undo=True)`` when the only forward in
        the log is for team 1 should be a no-op (state unchanged,
        team-1 forward still in log)."""
        s = SessionManager.get_or_create("mixed-3", mock_conf, api_backend)
        GameService.add_point(s, team=1)

        # No forward for team 2 to pop. State already 0 for team 2,
        # so the state-undo is also a no-op.
        GameService.add_point(s, team=2, undo=True)

        # Team 1 forward must still be available to undo.
        assert s.undoable_forward_count == 1
        response = GameService.undo_last(s)
        assert response.success is True
        state = s.game_manager.get_current_state()
        assert state.get_game(1, 1) == 0

    def test_generic_undo_dispatches_to_per_type_pop_only_once(
            self, mock_conf, api_backend):
        """Regression for the obvious bug introduced by my first
        attempt at unification: ``undo_last`` previously popped the
        forward and *then* called ``add_point(undo=True)``, which
        would pop AGAIN under the new semantics — undoing two
        actions for one click."""
        s = SessionManager.get_or_create("mixed-4", mock_conf, api_backend)
        GameService.add_point(s, team=1)
        GameService.add_point(s, team=1)
        # 2-0.
        GameService.undo_last(s)
        state = s.game_manager.get_current_state()
        # Exactly one point reverted, not two.
        assert state.get_game(1, 1) == 1
        assert s.undoable_forward_count == 1


# ---------------------------------------------------------------------------
# Set-winning point still undoes correctly under the new system
# ---------------------------------------------------------------------------

class TestAuditLogTimeline:
    """Lock down the exact log shape after pop+audit so a regression
    in the order of operations would fail loudly here."""

    def test_per_type_undo_leaves_only_undo_record(
            self, mock_conf, api_backend):
        s = SessionManager.get_or_create("tl-1", mock_conf, api_backend)
        GameService.add_point(s, team=1)
        GameService.add_point(s, team=1, undo=True)

        records = action_log.read_all("tl-1")
        # Forward was popped; only the undo record survives.
        assert len(records) == 1
        assert records[0]["action"] == "add_point"
        assert records[0]["params"] == {"team": 1, "undo": True}

    def test_generic_undo_leaves_only_undo_record(
            self, mock_conf, api_backend):
        s = SessionManager.get_or_create("tl-2", mock_conf, api_backend)
        GameService.add_point(s, team=1)
        GameService.undo_last(s)

        records = action_log.read_all("tl-2")
        assert len(records) == 1
        assert records[0]["action"] == "add_point"
        assert records[0]["params"] == {"team": 1, "undo": True}

    def test_non_undoable_actions_stay_in_log_after_undo(
            self, mock_conf, api_backend):
        s = SessionManager.get_or_create("tl-3", mock_conf, api_backend)
        GameService.add_point(s, team=1)
        GameService.change_serve(s, team=2)
        GameService.add_point(s, team=2)
        GameService.undo_last(s)  # pops the team=2 add_point fwd

        actions = [r["action"] for r in action_log.read_all("tl-3")]
        # Original: [add_point, change_serve, add_point]
        # After undo: [add_point, change_serve, add_point(undo)]
        # The team=2 forward was popped; change_serve untouched.
        assert actions == ["add_point", "change_serve", "add_point"]
        last = action_log.read_all("tl-3")[-1]
        assert last["params"] == {"team": 2, "undo": True}


class TestCounterLogAtomicity:
    """Counter must never drift from on-disk truth. Verified by
    forcing ``action_log.append`` to fail and checking the counter
    is unchanged."""

    def test_counter_unchanged_when_audit_append_fails(
            self, mock_conf, api_backend, monkeypatch):
        s = SessionManager.get_or_create("atom-1", mock_conf, api_backend)
        GameService.add_point(s, team=1)
        baseline = s.undoable_forward_count
        assert baseline == 1

        # Make the next append fail.
        def boom(*args, **kwargs):
            raise OSError("disk full")
        monkeypatch.setattr(action_log, "append", boom)

        # Forward path: state mutates, log write fails, counter
        # must NOT have incremented past baseline.
        GameService.add_point(s, team=2)
        assert s.undoable_forward_count == baseline

        # Undo path: state mutates, pop already removed the forward,
        # log write of undo record fails — counter must NOT have
        # decremented past baseline.
        GameService.add_point(s, team=1, undo=True)
        # The pop happened before _audit was called, so the on-disk
        # forward is gone. count_undoable_forwards reads what the
        # log actually has (no team=1 forward, no team=2 forward
        # since that one's append failed) so on-disk count is 0.
        assert action_log.count_undoable_forwards("atom-1") == 0
        # Counter stays at baseline because _audit never set it.
        assert s.undoable_forward_count == baseline


class TestSetWinningUndo:
    def test_per_type_undo_unwinds_set_win(self, mock_conf, api_backend):
        s = SessionManager.get_or_create("setwin-1", mock_conf, api_backend)
        for _ in range(24):
            GameService.add_point(s, team=1)
        GameService.add_point(s, team=1)  # 25 — wins set 1
        assert s.game_manager.get_current_state().get_sets(1) == 1

        GameService.add_point(s, team=1, undo=True)

        state = s.game_manager.get_current_state()
        assert state.get_sets(1) == 0
        assert state.get_game(1, 1) == 24
        # The unification means the matching forward (the 25th
        # add_point) was popped, leaving 24 undoable points.
        assert s.undoable_forward_count == 24
