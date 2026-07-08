"""User account operations — the only place that mutates ``users`` rows.

Keeps username normalization/validation, password hashing, and the
admin-management flows (create, reset-to-temp, role/active changes, delete)
in one auditable surface. Raises :class:`UserError` for caller-fixable
problems (duplicate username, invalid input); routes translate those into
HTTP responses.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.passwords import generate_temp_password, hash_password, verify_password
from app.db.models.user import ROLE_ADMIN, ROLE_USER, User
from app.id_validation import OVERLAY_ID_PATTERN

MIN_PASSWORD_LENGTH = 8

# A structurally-real dummy scrypt record (16-byte salt, 32-byte derived key,
# default cost) used on the account-not-found path so it performs the same
# scrypt work as a genuine verify — closing the login timing side-channel.
# Built as a literal so we never pay an scrypt run at import time.
_DUMMY_PASSWORD_HASH = "scrypt$n=16384,r=8,p=1$" + "0" * 32 + "$" + "0" * 64


class UserError(ValueError):
    """A caller-fixable account error (duplicate, invalid input, ...)."""


def normalize_username(raw: str) -> str:
    """Lowercase, trim, and validate a username against the URL-safe charset."""
    if not isinstance(raw, str):
        raise UserError("Username is required.")
    username = raw.strip().lower()
    if not OVERLAY_ID_PATTERN.match(username):
        raise UserError(
            "Username must be 1–64 characters: letters, digits, dot, hyphen, "
            "or underscore (and not '.' or '..')."
        )
    return username


def _validate_password(password: str) -> None:
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
        raise UserError(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
        )


def get_by_username(db: Session, username: str) -> User | None:
    return db.execute(
        select(User).where(User.username == username.strip().lower())
    ).scalar_one_or_none()


def admin_exists(db: Session, *, exclude_user_id: int | None = None) -> bool:
    stmt = select(func.count()).select_from(User).where(User.role == ROLE_ADMIN)
    if exclude_user_id is not None:
        stmt = stmt.where(User.id != exclude_user_id)
    return db.execute(stmt).scalar_one() > 0


def _normalize_email(email: str | None) -> str | None:
    if email is None:
        return None
    email = email.strip()
    return email or None


def create_user(
    db: Session,
    *,
    username: str,
    password: str,
    role: str = ROLE_USER,
    display_name: str | None = None,
    email: str | None = None,
    must_change_password: bool = False,
) -> User:
    """Create a user. Raises :class:`UserError` on duplicate/invalid input."""
    username = normalize_username(username)
    _validate_password(password)
    if role not in (ROLE_ADMIN, ROLE_USER):
        raise UserError("Invalid role.")
    if get_by_username(db, username) is not None:
        raise UserError("That username is already taken.")
    email = _normalize_email(email)
    if email is not None and db.execute(
        select(User).where(User.email == email)
    ).scalar_one_or_none() is not None:
        raise UserError("That email is already registered.")

    user = User(
        username=username,
        display_name=(display_name or "").strip() or None,
        email=email,
        password_hash=hash_password(password),
        role=role,
        is_active=True,
        must_change_password=must_change_password,
        password_changed_at=datetime.now(UTC),
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        # The pre-checks above race with concurrent inserts; translate the
        # unique-constraint loss into the same caller-fixable error instead
        # of surfacing a 500 (and leave the session usable again).
        db.rollback()
        raise UserError("That username or email is already taken.") from exc
    return user


def authenticate(db: Session, username: str, password: str) -> User | None:
    """Return the user iff *password* matches and the account is active."""
    user = get_by_username(db, username)
    if user is None or not user.is_active:
        # Still verify against a dummy hash to keep timing roughly uniform.
        verify_password(password, _DUMMY_PASSWORD_HASH)
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def set_password(db: Session, user: User, new_password: str) -> None:
    _validate_password(new_password)
    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    user.password_changed_at = datetime.now(UTC)
    db.flush()


def reset_to_temp_password(db: Session, user: User) -> str:
    """Set a random temp password and force a change on next login.

    Returns the plaintext temp password so the admin can hand it over.
    """
    temp = generate_temp_password()
    user.password_hash = hash_password(temp)
    user.must_change_password = True
    user.password_changed_at = datetime.now(UTC)
    db.flush()
    return temp


def update_profile(
    db: Session,
    user: User,
    *,
    display_name: str | None = None,
    email: str | None = None,
) -> User:
    if display_name is not None:
        user.display_name = display_name.strip() or None
    if email is not None:
        normalized = _normalize_email(email)
        if normalized is not None and normalized != user.email:
            clash = db.execute(
                select(User).where(User.email == normalized, User.id != user.id)
            ).scalar_one_or_none()
            if clash is not None:
                raise UserError("That email is already registered.")
        user.email = normalized
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise UserError("That email is already registered.") from exc
    return user


def delete_user(db: Session, user: User) -> None:
    """Delete a user; FK cascades remove their overlays/teams/presets/reports."""
    db.delete(user)
    db.flush()


def list_users(db: Session) -> list[User]:
    return list(
        db.execute(select(User).order_by(User.username)).scalars().all()
    )


def get_by_id(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def admin_count(db: Session) -> int:
    """Number of *usable* administrators (admin role AND active).

    Counts only active admins so the last-admin guards reflect who can
    actually administer the instance — a deactivated admin cannot resolve a
    session, so it must not keep the guards satisfied.
    """
    return int(
        db.execute(
            select(func.count()).select_from(User).where(
                User.role == ROLE_ADMIN, User.is_active.is_(True),
            )
        ).scalar_one()
    )


def is_last_active_admin(db: Session, user: User) -> bool:
    return user.role == ROLE_ADMIN and user.is_active and admin_count(db) <= 1


def set_role(db: Session, user: User, role: str) -> None:
    if role not in (ROLE_ADMIN, ROLE_USER):
        raise UserError("Invalid role.")
    # Refuse to demote the last usable admin so the instance can't be locked
    # out of administration.
    if role != ROLE_ADMIN and is_last_active_admin(db, user):
        raise UserError("Cannot demote the last administrator.")
    user.role = role
    db.flush()


def set_active(db: Session, user: User, active: bool) -> None:
    if not active and is_last_active_admin(db, user):
        raise UserError("Cannot deactivate the last administrator.")
    user.is_active = active
    db.flush()
