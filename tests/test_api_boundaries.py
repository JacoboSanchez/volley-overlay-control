"""Regression tests for shared API error and transaction boundaries."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.auth import service
from app.db.engine import after_commit, after_rollback, get_db

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
