"""Tests for app/api/session_persistence.py and the rehydrate path in
SessionManager.get_or_create.
"""
from unittest.mock import MagicMock

import pytest

from app.api import session_persistence
from app.api.session_manager import GameSession, SessionManager

pytestmark = pytest.mark.usefixtures("clean_sessions")


# Session-meta isolation comes from the autouse ``isolate_session_meta``
# fixture in tests/conftest.py.


# ---------------------------------------------------------------------------
# session_persistence module
# ---------------------------------------------------------------------------

class TestSessionPersistenceFile:
    def test_save_and_load_round_trip(self):
        session_persistence.save_session_meta(
            "oid-a", {"simple": True, "points_limit": 21}
        )
        loaded = session_persistence.load_session_meta("oid-a")
        assert loaded == {"simple": True, "points_limit": 21}

    def test_load_returns_none_when_absent(self):
        assert session_persistence.load_session_meta("never-saved") is None

    def test_invalid_oid_is_silently_ignored(self):
        # Path-traversal-y inputs and OIDs with separators must not produce
        # any file and load must return None.
        for bad in ("../escape", "with/slash", "", "a" * 200, "white space"):
            session_persistence.save_session_meta(bad, {"simple": True})
            assert session_persistence.load_session_meta(bad) is None

    def test_delete_removes_file(self):
        session_persistence.save_session_meta("oid-b", {"sets_limit": 3})
        assert session_persistence.delete_session_meta("oid-b") is True
        assert session_persistence.load_session_meta("oid-b") is None
        # Idempotent: second delete returns False but does not raise.
        assert session_persistence.delete_session_meta("oid-b") is False

    def test_meta_payload_includes_oid_marker(self):
        import json
        import os
        session_persistence.save_session_meta(
            "oid-c", {"simple": False, "sets_limit": 5}
        )
        data_dir = session_persistence._data_dir()
        files = [f for f in os.listdir(data_dir) if f.startswith("session_meta_")]
        assert len(files) == 1
        with open(os.path.join(data_dir, files[0]), encoding="utf-8") as f:
            payload = json.load(f)
        assert payload["_meta"]["oid"] == "oid-c"
        assert payload["sets_limit"] == 5


# ---------------------------------------------------------------------------
# GameSession.to_meta_dict / apply_meta
# ---------------------------------------------------------------------------

def _backend_for(model: dict | None = None):
    backend = MagicMock()
    backend.get_current_model.return_value = model or {}
    backend.get_current_customization.return_value = {}
    backend.is_visible.return_value = True
    backend.is_custom_overlay.return_value = False
    return backend


class TestGameSessionMeta:
    def test_to_meta_dict_captures_session_flags(self, mock_conf):
        session = GameSession("oid", mock_conf, _backend_for())
        session.simple = True
        session.points_limit = 21
        meta = session.to_meta_dict()
        assert meta == {
            "simple": True,
            "points_limit": 21,
            "points_limit_last_set": session.points_limit_last_set,
            "sets_limit": session.sets_limit,
            "match_started_at": session.match_started_at,
        }

    def test_apply_meta_restores_fields(self, mock_conf):
        session = GameSession("oid", mock_conf, _backend_for())
        session.apply_meta({
            "simple": True,
            "points_limit": 21,
            "points_limit_last_set": 11,
            "sets_limit": 3,
        })
        assert session.simple is True
        assert session.points_limit == 21
        assert session.points_limit_last_set == 11
        assert session.sets_limit == 3

    def test_apply_meta_ignores_invalid_values(self, mock_conf):
        session = GameSession("oid", mock_conf, _backend_for())
        original = session.points_limit
        session.apply_meta({"points_limit": "not-an-int"})
        assert session.points_limit == original

    def test_apply_meta_ignores_non_dict(self, mock_conf):
        session = GameSession("oid", mock_conf, _backend_for())
        original = session.simple
        session.apply_meta(None)  # type: ignore[arg-type]
        session.apply_meta("garbage")  # type: ignore[arg-type]
        assert session.simple == original


# ---------------------------------------------------------------------------
# SessionManager.get_or_create rehydrate
# ---------------------------------------------------------------------------

class TestSessionManagerRehydrate:
    def test_meta_is_persisted_when_limits_change(self, mock_conf, api_backend):
        SessionManager.get_or_create(
            "oid-rehydrate", mock_conf, api_backend, points_limit=21,
            points_limit_last_set=11, sets_limit=3,
        )
        loaded = session_persistence.load_session_meta("oid-rehydrate")
        assert loaded is not None
        assert loaded["points_limit"] == 21
        assert loaded["sets_limit"] == 3

    def test_session_restored_after_clear(self, mock_conf, api_backend):
        # First session: persist non-default limits.
        s1 = SessionManager.get_or_create(
            "oid-restart", mock_conf, api_backend, points_limit=21,
            points_limit_last_set=11, sets_limit=3,
        )
        s1.simple = True
        s1.persist_meta()

        # Simulate restart: drop the in-memory session table.
        SessionManager.clear()

        # Second session: no kwargs → should pick up the persisted values.
        s2 = SessionManager.get_or_create("oid-restart", mock_conf, api_backend)
        assert s2.points_limit == 21
        assert s2.points_limit_last_set == 11
        assert s2.sets_limit == 3
        assert s2.simple is True

    def test_explicit_kwargs_win_over_persisted(self, mock_conf, api_backend):
        s1 = SessionManager.get_or_create(
            "oid-override", mock_conf, api_backend, points_limit=21,
            sets_limit=3,
        )
        assert s1.points_limit == 21
        SessionManager.clear()

        s2 = SessionManager.get_or_create(
            "oid-override", mock_conf, api_backend, points_limit=15,
        )
        assert s2.points_limit == 15  # explicit kwarg wins
        assert s2.sets_limit == 3      # restored from disk

    def test_save_and_broadcast_persists_meta(self, mock_conf, api_backend):
        from app.api.game_service import GameService

        session = SessionManager.get_or_create(
            "oid-svc", mock_conf, api_backend,
        )
        session.simple = True
        GameService._save_and_broadcast(session)

        loaded = session_persistence.load_session_meta("oid-svc")
        assert loaded is not None
        assert loaded["simple"] is True
