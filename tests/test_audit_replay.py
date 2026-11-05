"""The audit log as source of truth: replaying history rebuilds live state."""

from __future__ import annotations

import random

import pytest

from app.api import action_log
from app.api.audit_replay import check_consistency, compare, replay
from app.api.game_service import GameService
from app.api.session_manager import SessionManager
from app.state import State

pytestmark = pytest.mark.usefixtures("clean_sessions")


def _rec(action, current_set, t1, t2, *, score_set=None, serve="A", params=None, t1_to=0, t2_to=0,
         t1_sets=0, t2_sets=0):
    result = {
        "current_set": current_set,
        "match_finished": False,
        "team_1": {"sets": t1_sets, "score": t1, "timeouts": t1_to},
        "team_2": {"sets": t2_sets, "score": t2, "timeouts": t2_to},
        "serve": serve,
    }
    if score_set is not None:
        result["score_set"] = score_set
    return {"ts": 0.0, "action": action, "params": params or {}, "result": result}


class TestReplayFold:
    def test_empty_log_is_blank_and_never_divergent(self):
        out = replay([])
        assert out.records == 0
        assert out.state.get_current_model() == State().get_current_model()
        live = State()
        live.set_game(1, 1, 9)
        assert compare(out, live) == []

    def test_set_winning_point_lands_in_the_closed_set(self):
        out = replay([
            _rec("add_point", 1, 24, 20),
            # Set won: current_set advanced, score_set still names set 1.
            _rec("add_point", 2, 25, 20, score_set=1, t1_sets=1),
            _rec("add_point", 2, 0, 1, serve="B", t1_sets=1),
        ])
        s = out.state
        assert (s.get_game(1, 1), s.get_game(2, 1)) == (25, 20)
        assert (s.get_game(1, 2), s.get_game(2, 2)) == (0, 1)
        assert s.get_sets(1) == 1
        assert s.get_current_set() == 2
        assert s.get_current_serve() == State.SERVE_2
        assert out.covered_sets == {1, 2}

    def test_manual_score_edit_in_another_set_comes_from_params(self):
        out = replay([
            _rec("add_point", 2, 3, 0),
            _rec("set_score", 2, 3, 0, params={"team": 2, "set_number": 1, "value": 23}),
        ])
        assert out.state.get_game(2, 1) == 23
        assert 1 in out.covered_sets

    def test_reset_restarts_the_fold(self):
        out = replay([
            _rec("add_point", 1, 10, 0),
            _rec("reset", 1, 0, 0, serve="None"),
            _rec("add_point", 1, 0, 1, serve="B"),
        ])
        assert out.starts_at_reset is True
        assert out.state.get_game(1, 1) == 0
        assert out.state.get_game(2, 1) == 1

    def test_per_set_timeouts_survive_set_change(self):
        out = replay([
            _rec("add_timeout", 1, 5, 5, t1_to=2),
            # The set-winning point's snapshot still reports set 1's
            # timeouts (it is audited before the state moves on).
            _rec("add_point", 2, 25, 23, score_set=1, t1_sets=1, t1_to=2),
            _rec("add_point", 2, 0, 1, t1_sets=1),
        ])
        assert out.state.get_timeout(1, 1) == 2
        assert out.state.get_timeout(1, 2) == 0

    def test_records_without_a_snapshot_are_skipped(self):
        out = replay([
            {"ts": 1.0, "action": "start_match", "params": {}},
            {"ts": 2.0, "action": "add_point", "result": {"current_set": 99}},
            _rec("add_point", 1, 1, 0),
        ])
        assert out.records == 3
        assert out.skipped == 2
        assert out.state.get_game(1, 1) == 1

    def test_divergence_names_the_field(self):
        records = [_rec("add_point", 1, 4, 2)]
        live = State()
        live.set_game(1, 1, 5)
        live.set_game(1, 2, 2)
        live.set_current_serve(State.SERVE_1)
        report = check_consistency(records, live)
        assert report["consistent"] is False
        assert report["divergences"] == [
            {"field": "score", "set_number": 1, "team": 1, "replayed": 4, "live": 5},
        ]

    def test_uncovered_sets_are_not_compared(self):
        """Retention pruning can drop early sets; they are not divergence."""
        records = [_rec("add_point", 3, 1, 0, t1_sets=1, t2_sets=1)]
        live = State()
        live.set_current_set(3)
        live.set_sets(1, 1)
        live.set_sets(2, 1)
        live.set_game(1, 1, 25)  # set 1 history was pruned
        live.set_game(3, 1, 1)
        live.set_current_serve(State.SERVE_1)
        report = check_consistency(records, live)
        assert report["consistent"] is True
        assert report["covered_sets"] == [3]


class TestReplayMatchesLiveState:
    """Random walks through the real GameService must always replay exactly.

    This is the invariant that makes the log a source of truth: if any
    mutation path forgot to audit, or audited a snapshot that does not
    describe its effect, some walk ends with a divergence naming the field.
    """

    ACTIONS = (
        "point1", "point2", "point1", "point2", "point1", "point2",
        "undo_point1", "undo_point2", "undo_last",
        "timeout1", "timeout2", "undo_timeout1",
        "serve1", "serve2",
    )
    # Manual corrections can put the board in states the scoring rules
    # never produce (a won set left current, say), where an undo is no
    # longer an exact inverse; that drift is what the consistency endpoint
    # exists to flag. Without undos in between, though, every correction's
    # snapshot must still replay exactly.
    CORRECTION_ACTIONS = (
        "point1", "point2", "point1", "point2",
        "timeout1", "timeout2", "serve1", "serve2",
        "set_score", "set_sets", "rules",
    )

    def _step(self, session, rng, action):
        if action == "point1":
            GameService.add_point(session, team=1)
        elif action == "point2":
            GameService.add_point(session, team=2)
        elif action == "undo_point1":
            GameService.add_point(session, team=1, undo=True)
        elif action == "undo_point2":
            GameService.add_point(session, team=2, undo=True)
        elif action == "undo_last":
            GameService.undo_last(session)
        elif action == "timeout1":
            GameService.add_timeout(session, team=1)
        elif action == "timeout2":
            GameService.add_timeout(session, team=2)
        elif action == "undo_timeout1":
            GameService.add_timeout(session, team=1, undo=True)
        elif action == "serve1":
            GameService.change_serve(session, team=1)
        elif action == "serve2":
            GameService.change_serve(session, team=2)
        elif action == "set_score":
            GameService.set_score(
                session, rng.choice((1, 2)), rng.randint(1, session.sets_limit),
                rng.randint(0, 26),
            )
        elif action == "set_sets":
            GameService.set_sets_value(session, rng.choice((1, 2)), rng.randint(0, 2))
        elif action == "rules":
            GameService.set_rules(session, sets_limit=rng.choice((3, 5)))

    def _walk(self, seed, actions, mock_conf, api_backend, monkeypatch, mode=None):
        from app.api import game_rapid_pair

        # Drive the clock so some undos land inside the rapid-pair window
        # (collapsing via tombstone + restore) and some outside it.
        clock = [1_000_000.0]
        monkeypatch.setattr(game_rapid_pair.time, "time", lambda: clock[0])
        rng = random.Random(seed)
        oid = f"replay-{seed}"
        session = SessionManager.get_or_create(oid, mock_conf, api_backend)
        GameService.reset(session)
        if mode is not None:
            GameService.set_rules(session, mode=mode, reset_to_defaults=True)
        compare_serve = session.mode != "table_tennis"
        for step in range(150):
            clock[0] += rng.choice((0.5, 2.0, 7.0))
            action = rng.choice(actions)
            self._step(session, rng, action)
            report = check_consistency(
                action_log.read_all(oid), session.game_manager.get_current_state(),
                compare_serve=compare_serve,
            )
            assert report["consistent"], (seed, step, action, report["divergences"])
        assert report["starts_at_reset"] is True

    @pytest.mark.parametrize("seed", range(40))
    def test_play_with_undos_replays_exactly(self, seed, mock_conf, api_backend, monkeypatch):
        self._walk(seed, self.ACTIONS, mock_conf, api_backend, monkeypatch)

    @pytest.mark.parametrize("mode", ["beach", "table_tennis"])
    @pytest.mark.parametrize("seed", range(10))
    def test_other_rule_modes_replay_exactly(self, seed, mode, mock_conf, api_backend, monkeypatch):
        """Table tennis derives its serve after the snapshot, so serve is the
        one field the check leaves out there (``compare_serve=False``)."""
        self._walk(seed, self.ACTIONS, mock_conf, api_backend, monkeypatch, mode=mode)

    @pytest.mark.parametrize("seed", range(20))
    def test_manual_corrections_replay_exactly(self, seed, mock_conf, api_backend, monkeypatch):
        self._walk(seed, self.CORRECTION_ACTIONS, mock_conf, api_backend, monkeypatch)


class TestUndoAfterManualCorrection:
    """A correction can leave the newest forward with nothing to reverse;
    the generic undo must walk past it instead of sticking on it."""

    def test_undo_last_skips_a_point_the_correction_already_removed(
        self, mock_conf, api_backend,
    ):
        session = SessionManager.get_or_create("stale-pt", mock_conf, api_backend)
        GameService.reset(session)
        GameService.add_point(session, team=2)
        GameService.add_point(session, team=1)
        GameService.set_score(session, 1, 1, 0)  # operator zeroes team 1
        state = session.game_manager.get_current_state()
        assert (state.get_game(1, 1), state.get_game(2, 1)) == (0, 1)

        res = GameService.undo_last(session)
        assert res.success
        assert (state.get_game(1, 1), state.get_game(2, 1)) == (0, 0)
        assert GameService.undo_last(session).success is False  # nothing reversible
        # The stale forward was walked past, not erased from the history.
        visible = action_log.read_all("stale-pt")
        assert any(
            r["action"] == "add_point" and r["params"] == {"team": 1, "undo": False}
            for r in visible
        )
        report = check_consistency(action_log.read_all("stale-pt"), state)
        assert report["consistent"], report["divergences"]

    def test_undo_last_skips_a_timeout_from_a_set_left_behind(
        self, mock_conf, api_backend,
    ):
        session = SessionManager.get_or_create("stale-to", mock_conf, api_backend)
        GameService.reset(session)
        GameService.add_point(session, team=2)
        GameService.add_timeout(session, team=1)
        GameService.set_sets_value(session, 1, 1)  # match moves to set 2
        state = session.game_manager.get_current_state()
        assert state.get_game(2, 1) == 1

        assert GameService.undo_last(session).success
        assert state.get_game(2, 1) == 0
        # The set-1 timeout is still on the board, so it must stay in the
        # history that reports and live stats count timeouts from.
        assert state.get_timeout(1, 1) == 1
        visible = action_log.read_all("stale-to")
        assert sum(
            1 for r in visible
            if r["action"] == "add_timeout" and not r["params"].get("undo")
        ) == 1
        report = check_consistency(visible, state)
        assert report["consistent"], report["divergences"]


class TestConsistencyEndpoint:
    def test_owner_sees_a_consistent_match(self, auth_client):
        client = auth_client
        client.post("/api/v1/session/init", json={"oid": "replay-ep"})
        for team in (1, 1, 2):
            client.post("/api/v1/game/add-point?oid=replay-ep", json={"team": team})
        res = client.get("/api/v1/audit/consistency?oid=replay-ep")
        assert res.status_code == 200
        body = res.json()
        assert body["consistent"] is True
        assert body["records"] >= 3
        assert 1 in body["covered_sets"]

    def test_drift_is_reported(self, auth_client):
        client = auth_client
        client.post("/api/v1/session/init", json={"oid": "replay-drift"})
        client.post("/api/v1/game/add-point?oid=replay-drift", json={"team": 1})
        # Mutate live state behind the audit log's back.
        skey = next(k for k in SessionManager._sessions if k.endswith(":replay-drift"))
        SessionManager._sessions[skey].game_manager.get_current_state().set_game(1, 1, 9)
        body = client.get("/api/v1/audit/consistency?oid=replay-drift").json()
        assert body["consistent"] is False
        assert {"field": "score", "set_number": 1, "team": 1, "replayed": 1, "live": 9} in (
            body["divergences"]
        )

    def test_requires_a_board_credential(self, app_client):
        assert app_client.get("/api/v1/audit/consistency?oid=x").status_code in (401, 403)
