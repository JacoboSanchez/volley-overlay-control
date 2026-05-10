"""Tests for the rapid-pair undo flow.

When the operator does an ``add_point`` and then the opposite-kind
``add_point`` on the same team within ``RAPID_PAIR_WINDOW_S`` (5 s by
default), the two actions collapse into a no-op at the audit-log
level. Concretely:

* tap → double-tap-undo within 5 s ⇒ neither half lands in the
  audit log (the just-added forward is tombstoned, no undo is
  appended).
* double-tap-undo → tap within 5 s ⇒ the original forward (which
  the undo had hidden) is restored and the just-written undo is
  tombstoned.

Outside the 5 s window or on a different team the actions remain
separate. Any non-``add_point`` mutation (``add_set``,
``add_timeout``, ``change_serve``, ``set_score``,
``set_sets_value``, ``reset``) invalidates the cache so a follow-up
tap can never trigger a false-positive recovery.

State-level effects (set-end, match-end, serve change) still fire
on the recovery side: the underlying transition really happened
(the operator briefly closed the set, then reopened it) and
downstream consumers should see the same edge.
"""
from __future__ import annotations

import pytest

from app.api import action_log
from app.api.game_service import GameService

pytestmark = pytest.mark.usefixtures("clean_sessions")


def _visible_records(oid: str) -> list[dict]:
    """Records the audit reducers (report, drawer) actually see —
    after ``_apply_tombstones`` has hidden popped / restored entries.
    """
    return action_log.read_all(oid)


def _add_points(session, team: int, n: int) -> None:
    for _ in range(n):
        GameService.add_point(session, team=team)


def _clear_match_clock(session):
    """Reset ``match_started_at`` so the next ``start_match`` exits
    the idempotent fast-path and runs its real body (including the
    rapid-pair invalidation we're testing). Returns *session* for
    use in lambdas.
    """
    session.match_started_at = None
    return session


# ---------------------------------------------------------------------------
# Case A — tap forward, then double-tap-undo within 5 s.
# ---------------------------------------------------------------------------


class TestRapidPairCaseA:
    def test_pair_collapses_to_empty_audit(self, api_session):
        # No audit lines before the pair.
        assert _visible_records(api_session.oid) == []

        GameService.add_point(api_session, team=1)
        # Forward landed in the audit + the cache is seeded.
        recs_after_forward = _visible_records(api_session.oid)
        assert len(recs_after_forward) == 1
        assert recs_after_forward[0]["params"] == {"team": 1, "undo": False}

        GameService.add_point(api_session, team=1, undo=True)
        # Pair collapses: nothing visible in the audit.
        assert _visible_records(api_session.oid) == []
        # State returned to baseline.
        state = GameService.get_state(api_session)
        assert state.team_1.scores["set_1"] == 0
        # Counter back to 0 — no undoable forwards left.
        assert api_session.undoable_forward_count == 0
        # Cache cleared so a follow-up tap acts as a fresh forward.
        assert 1 not in api_session.rapid_pair_cache

    def test_pair_outside_window_renders_normally(
        self, api_session, monkeypatch,
    ):
        """Beyond ``RAPID_PAIR_WINDOW_S`` the cache entry is stale
        and ignored — the undo path falls back to the regular
        unified-undo flow that pops the forward and appends an
        orphan undo.
        """
        import time as _time

        from app.api import game_service as gs

        # Freeze time so we can step it forward by more than 5 s
        # between the two actions without slowing the test.
        clock = [1_000_000.0]
        monkeypatch.setattr(gs.time, "time", lambda: clock[0])
        monkeypatch.setattr(_time, "time", lambda: clock[0])

        GameService.add_point(api_session, team=1)
        clock[0] += gs.RAPID_PAIR_WINDOW_S + 0.1
        GameService.add_point(api_session, team=1, undo=True)

        records = _visible_records(api_session.oid)
        # Forward is tombstoned by the normal pop, undo lands as an
        # orphan record. The rapid-pair flow should NOT have run.
        kinds = [(r["action"], r["params"].get("undo", False)) for r in records]
        assert ("add_point", True) in kinds
        assert ("add_point", False) not in kinds


# ---------------------------------------------------------------------------
# Case B — earlier forward, double-tap-undo, tap within 5 s.
# ---------------------------------------------------------------------------


class TestRapidPairCaseB:
    def test_recovery_restores_original_forward(self, api_session, monkeypatch):
        """``Case B`` per the spec: an *older* forward gets undone
        and then recovered within the rapid-pair window. The
        original forward must come back from its tombstone (so the
        timeline keeps its original ts) and the freshly-written
        undo must disappear.

        Time has to be mocked because the prior forwards must lie
        outside the rapid-pair window — otherwise the undo pairs
        with the most recent forward as ``Case A`` instead.
        """
        import time as _time

        from app.api import game_service as gs

        clock = [1_000_000.0]
        monkeypatch.setattr(gs.time, "time", lambda: clock[0])
        monkeypatch.setattr(_time, "time", lambda: clock[0])

        # Four forwards landed well in the past — beyond the rapid-
        # pair window so the cache they seeded goes stale.
        _add_points(api_session, team=1, n=4)
        assert api_session.undoable_forward_count == 4
        clock[0] += gs.RAPID_PAIR_WINDOW_S + 1.0

        # Operator double-taps to undo the most recent (old) forward.
        # Cache is stale → normal undo path: tombstones the old
        # forward, appends an undo record. Counter drops to 3.
        GameService.add_point(api_session, team=1, undo=True)
        assert api_session.undoable_forward_count == 3
        state_after_undo = GameService.get_state(api_session)
        assert state_after_undo.team_1.scores["set_1"] == 3

        # The undo seeded a fresh cache entry. Within the rapid-pair
        # window, a forward tap triggers the Case B recovery.
        clock[0] += 1.0  # well within RAPID_PAIR_WINDOW_S
        GameService.add_point(api_session, team=1, undo=False)

        state_after_recovery = GameService.get_state(api_session)
        assert state_after_recovery.team_1.scores["set_1"] == 4
        # All four originals visible; no undo / orphan / new forward.
        records = _visible_records(api_session.oid)
        assert len(records) == 4
        for r in records:
            assert r["action"] == "add_point"
            assert r["params"] == {"team": 1, "undo": False}
        # Counter is back to four undoable forwards.
        assert api_session.undoable_forward_count == 4
        # Cache cleared — the recovery wasn't re-seeded so a future
        # double-tap can't accidentally pair with anything.
        assert 1 not in api_session.rapid_pair_cache

    def test_recovery_for_different_team_does_not_pair(self, api_session):
        """A tap on team 2 right after a team-1 undo should NOT
        recover team 1's forward.
        """
        GameService.add_point(api_session, team=1)
        GameService.add_point(api_session, team=1, undo=True)
        # Cache now has team 1 — undo. Tap team 2:
        GameService.add_point(api_session, team=2)

        records = _visible_records(api_session.oid)
        kinds = [(r["params"].get("team"), r["params"].get("undo", False))
                 for r in records]
        # Team 1 pair already collapsed (case A from earlier) —
        # only the team 2 forward should remain.
        assert kinds == [(2, False)]


# ---------------------------------------------------------------------------
# Cache invalidation — non-add_point actions wipe the seed.
# ---------------------------------------------------------------------------


class TestRapidPairCacheInvalidation:
    @pytest.mark.parametrize("invalidator", [
        lambda s: GameService.add_set(s, team=1),
        lambda s: GameService.add_timeout(s, team=1),
        lambda s: GameService.change_serve(s, team=2),
        lambda s: GameService.set_score(s, team=1, set_number=1, value=10),
        lambda s: GameService.set_sets_value(s, team=1, value=1),
        lambda s: GameService.reset(s),
        lambda s: GameService.set_rules(s, points_limit=21),
        lambda s: GameService.start_match(_clear_match_clock(s)),
    ])
    def test_action_clears_rapid_pair_cache(self, api_session, invalidator):
        GameService.add_point(api_session, team=1)
        # Seed exists.
        assert 1 in api_session.rapid_pair_cache
        invalidator(api_session)
        # Seed gone.
        assert api_session.rapid_pair_cache == {}


# ---------------------------------------------------------------------------
# Set-winning + recovery: set-end side effect re-fires.
# ---------------------------------------------------------------------------


class TestRapidPairCounterAtomicity:
    """The in-memory ``undoable_forward_count`` must never drift
    from the on-disk audit log. The rapid-pair flow writes via
    ``tombstone_ts`` / ``restore_popped`` which return ``False``
    on I/O failure (instead of raising); the counter follows that
    return value so a failed write doesn't leave the cached count
    out of sync.
    """

    def test_case_a_skips_decrement_on_tombstone_failure(
        self, api_session, monkeypatch,
    ):
        from app.api import action_log as al

        GameService.add_point(api_session, team=1)
        baseline = api_session.undoable_forward_count
        assert baseline == 1

        # Force the rapid-pair Case A tombstone write to fail.
        monkeypatch.setattr(al, "tombstone_ts", lambda *a, **kw: False)

        GameService.add_point(api_session, team=1, undo=True)
        # The forward record stayed visible on disk because the
        # tombstone never landed; the counter must reflect that.
        assert api_session.undoable_forward_count == baseline

    def test_case_b_skips_increment_on_restore_failure(
        self, api_session, monkeypatch,
    ):
        import time as _time

        from app.api import action_log as al
        from app.api import game_service as gs

        clock = [1_000_000.0]
        monkeypatch.setattr(gs.time, "time", lambda: clock[0])
        monkeypatch.setattr(_time, "time", lambda: clock[0])

        GameService.add_point(api_session, team=1)
        clock[0] += gs.RAPID_PAIR_WINDOW_S + 0.1
        GameService.add_point(api_session, team=1, undo=True)
        baseline = api_session.undoable_forward_count
        # The (legacy) undo decremented the counter to zero.
        assert baseline == 0

        # Simulate a restore-write failure on the recovery tap.
        monkeypatch.setattr(al, "restore_popped", lambda *a, **kw: False)
        clock[0] += 1.0  # within the rapid-pair window of the undo
        GameService.add_point(api_session, team=1, undo=False)

        # Without a successful restore the original forward stays
        # tombstoned — the counter must not pretend it's undoable.
        assert api_session.undoable_forward_count == baseline

    def test_case_b_skips_restore_when_undo_tombstone_fails(
        self, api_session, monkeypatch,
    ):
        """If the Case B tombstone of the undo record fails, we must
        NOT restore the original forward. Otherwise the audit log
        ends up with a visible orphan undo + a visible restored
        forward, and ``_collapse_undos`` in the report would pair
        them and hide both — defeating the recovery.
        """
        import time as _time

        from app.api import action_log as al
        from app.api import game_service as gs

        clock = [1_000_000.0]
        monkeypatch.setattr(gs.time, "time", lambda: clock[0])
        monkeypatch.setattr(_time, "time", lambda: clock[0])

        GameService.add_point(api_session, team=1)
        clock[0] += gs.RAPID_PAIR_WINDOW_S + 0.1
        GameService.add_point(api_session, team=1, undo=True)
        baseline = api_session.undoable_forward_count
        assert baseline == 0
        # After the legacy undo the audit log shows the orphan undo
        # only; the original forward is tombstoned.
        records_after_undo = _visible_records(api_session.oid)
        assert len(records_after_undo) == 1
        assert records_after_undo[0]["params"] == {"team": 1, "undo": True}

        # Track restore attempts so we can assert the recovery bailed
        # out before touching the on-disk forward.
        restore_calls: list[tuple] = []
        real_restore = al.restore_popped

        def _fail_tombstone(*_a, **_kw):
            return False

        def _spy_restore(*args, **kwargs):
            restore_calls.append((args, kwargs))
            return real_restore(*args, **kwargs)

        monkeypatch.setattr(al, "tombstone_ts", _fail_tombstone)
        monkeypatch.setattr(al, "restore_popped", _spy_restore)

        clock[0] += 1.0  # within the rapid-pair window of the undo
        GameService.add_point(api_session, team=1, undo=False)

        # Restore must not have been attempted — otherwise the report
        # would see (visible undo + visible forward) and collapse them.
        assert restore_calls == []
        # Counter is unchanged since neither write succeeded.
        assert api_session.undoable_forward_count == baseline


class TestRapidPairSetWinning:
    def test_set_winning_recovery_re_advances_current_set(self, api_session):
        """A set-winning point that gets undone then immediately
        recovered must end with ``current_set`` advanced again.
        Mirrors the live behaviour: the operator briefly thought
        the set wasn't over, changed their mind, and the report
        should still show the set as closed.
        """
        # Bring team 1 to set point: 24-23 in set 1.
        GameService.set_score(api_session, team=1, set_number=1, value=24)
        GameService.set_score(api_session, team=2, set_number=1, value=23)
        # Re-seed cache after set_score invalidation: rack one
        # forward so the rapid-pair entry exists for the next undo.
        # (Without this, the eventual undo's set-winning pop would
        # find no match.) Bring T1 to 25 to win the set.
        GameService.add_point(api_session, team=1)
        # The forward winning the set advanced ``current_set``.
        assert api_session.current_set == 2

        # Operator double-taps to undo the set-winning point.
        GameService.add_point(api_session, team=1, undo=True)
        assert api_session.current_set == 1

        # Within 5 s, taps to restore. Set ends again, current_set
        # advances back to 2.
        GameService.add_point(api_session, team=1)
        assert api_session.current_set == 2
        # The audit log keeps a single visible forward for the
        # set-winning point — the rapid pair restored the original.
        records = _visible_records(api_session.oid)
        # One forward visible (the set-winning point).
        assert any(
            r["action"] == "add_point" and not r["params"].get("undo")
            for r in records
        )
        # No undo / orphan recovery record.
        assert all(
            not (r["action"] == "add_point" and r["params"].get("undo"))
            for r in records
        )
