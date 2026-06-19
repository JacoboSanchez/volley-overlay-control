"""FastAPI auth dependencies — the cookie-session replacement for the
env-var Bearer ladder.

Dependency layering:

* ``current_user``           — resolve the cookie session, or ``None``.
* ``current_user_or_401``    — same, but 401 when unauthenticated. Does NOT
                               enforce the must-change-password gate (so the
                               change-password / logout / me endpoints stay
                               reachable mid-rotation).
* ``require_user``           — ``current_user_or_401`` + 409 when the account
                               still owes a password change.
* ``require_admin``          — ``require_user`` + 403 unless the role is admin.
"""

from __future__ import annotations

from fastapi import Cookie, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import sessions
from app.db.engine import get_db
from app.db.models.user import User

_WWW_AUTH = {"WWW-Authenticate": "Cookie"}
PASSWORD_CHANGE_REQUIRED = "password_change_required"


def current_user(
    vsession: str | None = Cookie(None),
    db: Session = Depends(get_db),
) -> User | None:
    """Resolve the logged-in user from the session cookie, or ``None``."""
    return sessions.resolve_session(db, vsession)


def current_user_or_401(user: User | None = Depends(current_user)) -> User:
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated.", headers=_WWW_AUTH)
    return user


def require_user(user: User = Depends(current_user_or_401)) -> User:
    """Authenticated, active, and not pending a forced password change."""
    if user.must_change_password:
        raise HTTPException(status_code=409, detail=PASSWORD_CHANGE_REQUIRED)
    return user


def require_admin(user: User = Depends(require_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Administrator access required.")
    return user
