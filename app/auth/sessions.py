"""Opaque-token cookie sessions, stored hashed in the database.

The cookie carries a random ``secrets.token_urlsafe(32)`` value; only its
SHA-256 is persisted (mirroring how every other credential in the codebase
is stored hashed). Server-side storage is what makes logout, admin
password-reset, and "log out everywhere on password change" possible — a
stateless signed cookie could not be revoked without a denylist that would
itself be a DB table.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models.user import AuthSession, User
from app.env_vars_manager import EnvVarsManager, is_truthy

logger = logging.getLogger(__name__)

COOKIE_NAME = "vsession"
_TOKEN_BYTES = 32
_DEFAULT_TTL_HOURS = 24 * 14  # 14 days
# Only persist a ``last_seen_at`` bump this often, so authenticated reads
# don't turn into a DB write+commit on every request.
_LAST_SEEN_THROTTLE = timedelta(minutes=5)


def _now() -> datetime:
    return datetime.now(UTC)


def _ttl() -> timedelta:
    try:
        hours = int(EnvVarsManager.get_env_var("SESSION_TTL_HOURS", _DEFAULT_TTL_HOURS))
    except (TypeError, ValueError):
        hours = _DEFAULT_TTL_HOURS
    return timedelta(hours=max(1, hours))


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def create_session(
    db: Session,
    user: User,
    *,
    user_agent: str | None = None,
    ip: str | None = None,
) -> str:
    """Create a session row for *user* and return the raw cookie token."""
    raw = secrets.token_urlsafe(_TOKEN_BYTES)
    now = _now()
    db.add(
        AuthSession(
            user_id=user.id,
            token_hash=hash_token(raw),
            expires_at=now + _ttl(),
            last_seen_at=now,
            user_agent=(user_agent or "")[:255] or None,
            ip=(ip or "")[:64] or None,
        )
    )
    db.flush()
    return raw


def resolve_session(db: Session, raw: str | None) -> User | None:
    """Return the active user for a cookie token, or ``None``.

    Validates expiry and that the account is still active, and bumps
    ``last_seen_at``. Expired rows are dropped lazily.
    """
    if not raw:
        return None
    row = db.execute(
        select(AuthSession).where(AuthSession.token_hash == hash_token(raw))
    ).scalar_one_or_none()
    if row is None:
        return None
    expires_at = row.expires_at
    if expires_at.tzinfo is None:  # SQLite returns naive UTC datetimes
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= _now():
        db.delete(row)
        db.commit()
        return None
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        return None
    now = _now()
    last_seen = row.last_seen_at
    if last_seen is not None and last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=UTC)
    if last_seen is None or (now - last_seen) > _LAST_SEEN_THROTTLE:
        row.last_seen_at = now
        db.commit()
    return user


def revoke_session(db: Session, raw: str | None) -> None:
    if not raw:
        return
    db.execute(delete(AuthSession).where(AuthSession.token_hash == hash_token(raw)))
    db.commit()


def revoke_all_for_user(
    db: Session, user_id: int, *, except_token_hash: str | None = None,
) -> None:
    """Delete every session for *user_id*, optionally keeping one (the caller's)."""
    stmt = delete(AuthSession).where(AuthSession.user_id == user_id)
    if except_token_hash is not None:
        stmt = stmt.where(AuthSession.token_hash != except_token_hash)
    db.execute(stmt)
    db.commit()


def cookie_secure(scheme: str | None = None) -> bool:
    """Whether to set the ``Secure`` cookie flag.

    ``SESSION_COOKIE_SECURE`` forces the value when set. Otherwise the flag
    follows the request scheme: ``Secure`` over HTTPS, off over plain HTTP so
    local/LAN dev (and the test client) work. Operators behind a TLS-
    terminating proxy that forwards as HTTP should set
    ``SESSION_COOKIE_SECURE=true`` (and enable proxy headers).
    """
    raw = EnvVarsManager.get_env_var("SESSION_COOKIE_SECURE", None)
    if raw is not None:
        return is_truthy(raw if isinstance(raw, str) else str(raw))
    return scheme == "https"


def set_session_cookie(response: Response, raw: str, *, secure: bool = True) -> None:
    response.set_cookie(
        COOKIE_NAME,
        raw,
        max_age=int(_ttl().total_seconds()),
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")
