"""Regression tests for shared API error and transaction boundaries."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app import overlays_service
from app.api import session_persistence
from app.api.dependencies import BoardAccess
from app.api.routes.session import init_session
from app.api.schemas import InitRequest
from app.api.session_manager import SessionManager
from app.auth import service
from app.db.engine import after_commit, after_rollback, get_db
from app.db.models.user import User
from app.overlay import overlay_state_store
from app.state import State
from tests.conftest import load_fixture

ROOT = Path(__file__).resolve().parents[1]


def test_route_modules_do_not_commit_request_sessions() -> None:
    """Writes are committed by ``get_db``, not selected route handlers."""
    route_files = [
        *sorted((ROOT / "app/api/routes").glob("*.py")),
        ROOT / "app/auth/routes.py",
    ]
    offenders = [
        path.relative_to(ROOT)
        for path in route_files
        if "db.commit()" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []


def test_get_db_commits_and_runs_post_commit_callbacks(db_session) -> None:
    dependency = get_db()
    request_db = next(dependency)
    events: list[str] = []

    service.create_user(
        request_db,
        username="transaction-success",
        password="password123",
    )
    after_commit(request_db, lambda: events.append("commit"))
    after_rollback(request_db, lambda: events.append("rollback"))

    with pytest.raises(StopIteration):
        next(dependency)

    db_session.expire_all()
    assert service.get_by_username(db_session, "transaction-success") is not None
    assert events == ["commit"]


def test_get_db_rolls_back_and_runs_rollback_callbacks(db_session) -> None:
    dependency = get_db()
    request_db = next(dependency)
    events: list[str] = []

    service.create_user(
        request_db,
        username="transaction-failure",
        password="password123",
    )
    after_commit(request_db, lambda: events.append("commit"))
    after_rollback(request_db, lambda: events.append("rollback"))

    with pytest.raises(RuntimeError, match="handler failed"):
        dependency.throw(RuntimeError("handler failed"))

    db_session.expire_all()
    assert service.get_by_username(db_session, "transaction-failure") is None
    assert events == ["rollback"]


@pytest.mark.usefixtures("clean_sessions")
@pytest.mark.asyncio
async def test_owner_init_commit_failure_discards_auto_created_runtime(
    monkeypatch,
    db_session,
) -> None:
    """A failed overlay-row commit cannot leave a session using its old token."""
    owner = service.create_user(
        db_session,
        username="overlay-rollback-owner",
        password="password123",
    )
    db_session.commit()

    dependency = get_db()
    request_db = next(dependency)
    request_owner = request_db.get(User, owner.id)
    assert request_owner is not None

    backend = MagicMock()
    backend.validate_and_store_model_for_oid.return_value = State.OIDStatus.VALID
    backend.fetch_output_token.return_value = None
    backend.get_current_model.return_value = load_fixture("base_model")
    backend.get_current_customization.return_value = load_fixture("base_customization")
    backend.is_visible.return_value = True
    skey = f"{owner.id}:commit-failure"

    access = BoardAccess(
        token=None,
        public_user=None,
        user=request_owner,
        db=request_db,
    )
    with patch("app.api.routes.session.Backend", return_value=backend):
        response = await init_session(InitRequest(oid="commit-failure"), access)

    assert response.success is True
    assert SessionManager.peek(skey) is not None
    assert session_persistence.load_session_meta(skey) is not None
    assert overlay_state_store.overlay_exists(skey)

    def failing_commit() -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr(request_db, "commit", failing_commit)
    with pytest.raises(RuntimeError, match="disk full"):
        next(dependency)

    db_session.expire_all()
    assert overlays_service.get_overlay(
        db_session,
        owner.id,
        "commit-failure",
    ) is None
    assert SessionManager.peek(skey) is None
    assert session_persistence.load_session_meta(skey) is None
    assert not overlay_state_store.overlay_exists(skey)
