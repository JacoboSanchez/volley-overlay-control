"""Tests for app/api/match_archive.py (DB-backed) and the archive trigger."""
import time

import pytest

from app.api import action_log, match_archive
from app.api.game_service import GameService
from app.api.session_manager import SessionManager
from app.overlay_key import make_skey

pytestmark = pytest.mark.usefixtures("clean_sessions")


def _user_skey(db_session, oid, username="archuser"):
    """Create (or reuse) a user and return ``(user_id, skey)`` for *oid*.

    Match reports key on a real user (FK), so archival requires a storage
    key whose user exists.
    """
    from app.auth import service

    user = service.get_by_username(db_session, username) or service.create_user(
        db_session, username=username, password="password123",
    )
    db_session.commit()
    return user.id, make_skey(user.id, oid)


# ---------------------------------------------------------------------------
# match_archive low-level (DB-backed)
# ---------------------------------------------------------------------------

class TestMatchArchive:
    def test_archive_round_trip(self, db_session):
        _uid, skey = _user_skey(db_session, "oid-x")
        action_log.append(skey, "add_point", {"team": 1}, {"score": 1})
        match_id = match_archive.archive_match(
            oid=skey,
            final_state={"team_1": {"sets": 3}, "team_2": {"sets": 1},
                         "current_set": 4},
            customization={"Team 1 Name": "Home"},
            started_at=time.time() - 1800,
            winning_team=1,
            points_limit=25,
            points_limit_last_set=15,
            sets_limit=5,
        )
        assert match_id is not None

        loaded = match_archive.load_match(match_id)
        assert loaded is not None
        assert loaded["oid"] == skey
        assert loaded["winning_team"] == 1
        assert loaded["final_state"]["team_1"]["sets"] == 3
        assert loaded["customization"]["Team 1 Name"] == "Home"
        assert loaded["audit_log"][0]["action"] == "add_point"
        assert loaded["config"]["points_limit"] == 25
        assert loaded["duration_s"] is not None and loaded["duration_s"] > 0

    def test_non_storage_key_returns_none(self, db_session):
        # A bare oid (no owning user) cannot be archived.
        assert match_archive.archive_match(
            oid="oid-x", final_state={}, winning_team=1,
        ) is None
        assert match_archive.archive_match(
            oid="../escape", final_state={}, winning_team=1,
        ) is None

    def test_list_matches_filters_by_oid(self, db_session):
        _uid, skey_a = _user_skey(db_session, "oid-a")
        _uid2, skey_b = _user_skey(db_session, "oid-b")
        match_archive.archive_match(oid=skey_a, final_state={"current_set": 5}, winning_team=2)
        match_archive.archive_match(oid=skey_b, final_state={"current_set": 4}, winning_team=1)
        matches_a = match_archive.list_matches(oid=skey_a)
        assert len(matches_a) == 1
        assert matches_a[0]["oid"] == skey_a
        assert len(match_archive.list_matches()) == 2

    def test_list_matches_orders_newest_first(self, db_session):
        _uid, skey = _user_skey(db_session, "oid-ord")
        match_archive.archive_match(
            oid=skey, final_state={"team_1": {"sets": 0}, "team_2": {"sets": 3}}, winning_team=2)
        match_archive.archive_match(
            oid=skey, final_state={"team_1": {"sets": 3}, "team_2": {"sets": 1}}, winning_team=1)
        matches = match_archive.list_matches(oid=skey)
        assert matches[0]["winning_team"] == 1
        assert matches[1]["winning_team"] == 2

    def test_load_match_rejects_malformed_id(self, db_session):
        assert match_archive.load_match("../etc/passwd") is None
        assert match_archive.load_match("nope") is None
        assert match_archive.load_match("match_zzzz_invalid") is None
        assert match_archive.load_match(None) is None

    def test_back_to_back_archives_get_distinct_ids(self, db_session):
        _uid, skey = _user_skey(db_session, "oid-b2b")
        ids = {
            match_archive.archive_match(oid=skey, final_state={}, winning_team=1)
            for _ in range(5)
        }
        assert None not in ids
        assert len(ids) == 5

    def test_delete_for_oid_removes_rows(self, db_session):
        _uid, skey = _user_skey(db_session, "oid-del")
        for _ in range(3):
            match_archive.archive_match(oid=skey, final_state={}, winning_team=1)
        assert len(match_archive.list_matches(oid=skey)) == 3
        assert match_archive.delete_for_oid(skey) == 3
        assert match_archive.list_matches(oid=skey) == []

    def test_delete_match_removes_single_row(self, db_session):
        _uid, skey = _user_skey(db_session, "oid-single")
        a = match_archive.archive_match(oid=skey, final_state={}, winning_team=1)
        b = match_archive.archive_match(oid=skey, final_state={}, winning_team=2)
        assert a is not None and b is not None and a != b
        assert match_archive.delete_match(a) is True
        ids = {s["match_id"] for s in match_archive.list_matches(oid=skey)}
        assert ids == {b}

    def test_delete_match_returns_false_on_missing(self, db_session):
        assert match_archive.delete_match(
            "match_" + "0" * 20 + "_20260101T000000_000000Z") is False

    def test_delete_match_rejects_malformed_id(self, db_session):
        assert match_archive.delete_match("../etc/passwd") is False
        assert match_archive.delete_match("match_aaaaaaaaaaaaaaaaaaaa_../boom") is False
        assert match_archive.delete_match("") is False
        assert match_archive.delete_match(None) is False

    def test_other_users_archives_do_not_leak(self, db_session):
        _u1, skey1 = _user_skey(db_session, "shared", username="alice")
        _u2, skey2 = _user_skey(db_session, "shared", username="bob")
        match_archive.archive_match(oid=skey1, final_state={}, winning_team=1)
        # Same raw oid, different user → not visible to the other.
        assert len(match_archive.list_matches(oid=skey1)) == 1
        assert match_archive.list_matches(oid=skey2) == []


# ---------------------------------------------------------------------------
# GameService archive trigger
# ---------------------------------------------------------------------------

class TestArchiveTrigger:
    def _drive_to_match_end(self, session, *, via_set):
        """Helper: get the session to match_finished using add_set or add_point."""
        if via_set:
            for _ in range(3):
                GameService.add_set(session, team=1)
        else:
            # Score 25-0 three times.
            for _set_num in range(1, 4):
                # Each iteration: 25 points to team 1
                for _ in range(25):
                    GameService.add_point(session, team=1)

    def test_match_end_via_add_set_archives(self, mock_conf, api_backend, db_session):
        _uid, skey = _user_skey(db_session, "arch-1")
        session = SessionManager.get_or_create(skey, mock_conf, api_backend)
        # mock_conf: sets=5 → soft limit 3 → 3 sets win the match.
        self._drive_to_match_end(session, via_set=True)
        matches = match_archive.list_matches(oid=skey)
        assert len(matches) == 1
        assert matches[0]["winning_team"] == 1

    def test_match_end_via_add_point_archives(self, mock_conf, api_backend, db_session):
        _uid, skey = _user_skey(db_session, "arch-2")
        session = SessionManager.get_or_create(skey, mock_conf, api_backend)
        self._drive_to_match_end(session, via_set=False)
        matches = match_archive.list_matches(oid=skey)
        assert len(matches) == 1
        # Check the audit log was bundled in.
        full = match_archive.load_match(matches[0]["match_id"])
        assert any(r["action"] == "add_point" for r in full["audit_log"])

    def test_no_archive_when_match_in_progress(self, mock_conf, api_backend):
        session = SessionManager.get_or_create("arch-3", mock_conf, api_backend)
        GameService.add_set(session, team=1)
        GameService.add_set(session, team=2)
        assert match_archive.list_matches(oid="arch-3") == []

    def test_archive_failure_does_not_break_action(
            self, mock_conf, api_backend, monkeypatch):
        session = SessionManager.get_or_create("arch-4", mock_conf, api_backend)
        monkeypatch.setattr(
            match_archive, "archive_match",
            lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        # Drive to match end — even with archive throwing, the action
        # response should still succeed.
        for _ in range(2):
            GameService.add_set(session, team=1)
        response = GameService.add_set(session, team=1)
        assert response.success is True

    def test_match_started_at_starts_unarmed(self, mock_conf, api_backend):
        # Fresh session has no match anchor — operator (or first
        # point) arms it explicitly.
        session = SessionManager.get_or_create("arch-fresh", mock_conf, api_backend)
        assert session.match_started_at is None

    def test_match_started_at_persists_across_restart(
            self, mock_conf, api_backend):
        session = SessionManager.get_or_create("arch-5", mock_conf, api_backend)
        # First point implicitly arms the timer.
        GameService.add_point(session, team=1)
        original = session.match_started_at
        assert original is not None
        SessionManager.clear()

        restored = SessionManager.get_or_create("arch-5", mock_conf, api_backend)
        assert restored.match_started_at == pytest.approx(original)

    def test_match_started_at_clears_on_reset(self, mock_conf, api_backend):
        # Reset wipes the match — the next match starts unarmed
        # again, so the timer / report don't backdate the new run.
        session = SessionManager.get_or_create("arch-6", mock_conf, api_backend)
        GameService.add_point(session, team=1)
        assert session.match_started_at is not None
        GameService.reset(session)
        assert session.match_started_at is None

    def test_first_point_arms_match_started_at(self, mock_conf, api_backend):
        # The implicit-start path: a fresh session has no anchor; the
        # first ``add_point`` sets it to now.
        session = SessionManager.get_or_create("arch-arm", mock_conf, api_backend)
        assert session.match_started_at is None
        before = time.time()
        GameService.add_point(session, team=1)
        after = time.time()
        assert before <= session.match_started_at <= after

    def test_undo_does_not_arm_match_started_at(self, mock_conf, api_backend):
        # ``add_point`` with ``undo=True`` shouldn't backdoor the
        # implicit start; otherwise undoing the very first point
        # would leave a ghost-armed match.
        session = SessionManager.get_or_create("arch-no-arm", mock_conf, api_backend)
        GameService.add_point(session, team=1, undo=True)
        assert session.match_started_at is None

    def test_start_match_arms_explicitly(self, mock_conf, api_backend):
        session = SessionManager.get_or_create("arch-explicit",
                                               mock_conf, api_backend)
        assert session.match_started_at is None
        before = time.time()
        response = GameService.start_match(session)
        after = time.time()
        assert response.success is True
        assert before <= session.match_started_at <= after

    def test_start_match_is_idempotent(self, mock_conf, api_backend):
        # A second call must not re-anchor the clock — otherwise
        # double-clicking the button would reset the displayed timer.
        session = SessionManager.get_or_create("arch-idem", mock_conf, api_backend)
        GameService.start_match(session)
        first_anchor = session.match_started_at
        time.sleep(0.01)
        GameService.start_match(session)
        assert session.match_started_at == first_anchor

    def test_match_finished_at_stamped_on_match_end_via_add_set(
            self, mock_conf, api_backend):
        # The set-winning ``add_set`` that closes the match must
        # stamp ``match_finished_at`` *before* the broadcast so the
        # spectator/HUD timer can freeze at the actual end-of-match
        # value instead of ticking forward indefinitely.
        session = SessionManager.get_or_create(
            "arch-finished-set", mock_conf, api_backend,
        )
        GameService.start_match(session)
        before = time.time()
        self._drive_to_match_end(session, via_set=True)
        after = time.time()
        assert session.match_finished_at is not None
        assert before <= session.match_finished_at <= after
        # ``match_started_at`` survives the archive so the elapsed
        # duration is computable until the operator hits Reset.
        assert session.match_started_at is not None

    def test_match_finished_at_stamped_on_match_end_via_add_point(
            self, mock_conf, api_backend):
        session = SessionManager.get_or_create(
            "arch-finished-pt", mock_conf, api_backend,
        )
        before = time.time()
        self._drive_to_match_end(session, via_set=False)
        after = time.time()
        assert session.match_finished_at is not None
        assert before <= session.match_finished_at <= after
        assert session.match_started_at is not None

    def test_reset_clears_match_finished_at(self, mock_conf, api_backend):
        session = SessionManager.get_or_create(
            "arch-finished-reset", mock_conf, api_backend,
        )
        self._drive_to_match_end(session, via_set=True)
        assert session.match_finished_at is not None
        GameService.reset(session)
        assert session.match_finished_at is None
        assert session.match_started_at is None

    def test_match_finished_at_in_state_response(self, mock_conf, api_backend):
        session = SessionManager.get_or_create(
            "arch-finished-state", mock_conf, api_backend,
        )
        assert GameService.get_state(session).match_finished_at is None
        self._drive_to_match_end(session, via_set=True)
        state = GameService.get_state(session)
        assert state.match_finished is True
        assert state.match_finished_at is not None
        assert state.match_finished_at == session.match_finished_at

    def test_undo_of_match_winning_set_clears_match_finished_at(
            self, mock_conf, api_backend):
        # Regression: the React MatchTimer freezes purely on
        # ``finishedAt != null``, so leaving ``match_finished_at`` set
        # after an undo that reopens the match would keep the HUD
        # clock stuck on the old end-of-match value. The undo path
        # must clear the timestamp atomically with the match-finished
        # transition reversing.
        session = SessionManager.get_or_create(
            "arch-undo-set", mock_conf, api_backend,
        )
        self._drive_to_match_end(session, via_set=True)
        assert session.match_finished_at is not None
        GameService.add_set(session, team=1, undo=True)
        assert session.game_manager.match_finished(session.sets_limit) is False
        assert session.match_finished_at is None

    def test_undo_of_match_winning_point_clears_match_finished_at(
            self, mock_conf, api_backend):
        session = SessionManager.get_or_create(
            "arch-undo-pt", mock_conf, api_backend,
        )
        self._drive_to_match_end(session, via_set=False)
        assert session.match_finished_at is not None
        GameService.add_point(session, team=1, undo=True)
        assert session.game_manager.match_finished(session.sets_limit) is False
        assert session.match_finished_at is None

    def test_set_score_to_winning_value_stamps_match_finished_at(
            self, mock_conf, api_backend):
        # Regression: a manual ``set_score`` edit that pushes the
        # match across the finish line is just as much an end-of-
        # match transition as the natural add_point/add_set path, and
        # must stamp ``match_finished_at`` so the HUD timer freezes.
        session = SessionManager.get_or_create(
            "arch-setscore-finish", mock_conf, api_backend,
        )
        # Drive 2 sets to team 1 via add_set, then edit the deciding
        # set's score to the winning total directly.
        for _ in range(2):
            GameService.add_set(session, team=1)
        assert session.match_finished_at is None
        before = time.time()
        GameService.set_score(
            session, team=1, set_number=session.current_set, value=25,
        )
        after = time.time()
        assert session.game_manager.match_finished(session.sets_limit)
        assert session.match_finished_at is not None
        assert before <= session.match_finished_at <= after

    def test_set_sets_value_to_winning_count_stamps_match_finished_at(
            self, mock_conf, api_backend):
        session = SessionManager.get_or_create(
            "arch-setsvalue-finish", mock_conf, api_backend,
        )
        before = time.time()
        # sets_limit=5 → soft limit 3 wins the match.
        GameService.set_sets_value(session, team=1, value=3)
        after = time.time()
        assert session.game_manager.match_finished(session.sets_limit)
        assert session.match_finished_at is not None
        assert before <= session.match_finished_at <= after

    def test_set_sets_value_back_down_clears_match_finished_at(
            self, mock_conf, api_backend):
        session = SessionManager.get_or_create(
            "arch-setsvalue-revert", mock_conf, api_backend,
        )
        GameService.set_sets_value(session, team=1, value=3)
        assert session.match_finished_at is not None
        GameService.set_sets_value(session, team=1, value=2)
        assert session.game_manager.match_finished(session.sets_limit) is False
        assert session.match_finished_at is None

    def test_re_winning_after_undo_re_stamps_match_finished_at(
            self, mock_conf, api_backend):
        # After an undo + a fresh winning point the timestamp must
        # update to the *new* end-of-match wall clock, not bleed
        # through from the first attempt.
        session = SessionManager.get_or_create(
            "arch-undo-redo", mock_conf, api_backend,
        )
        self._drive_to_match_end(session, via_set=True)
        first_finished = session.match_finished_at
        assert first_finished is not None
        GameService.add_set(session, team=1, undo=True)
        assert session.match_finished_at is None
        time.sleep(0.01)
        GameService.add_set(session, team=1)
        assert session.match_finished_at is not None
        assert session.match_finished_at > first_finished
