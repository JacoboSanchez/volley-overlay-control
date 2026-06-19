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
from sqlalchemy.orm import Session

from app.auth.passwords import generate_temp_password, hash_password, verify_password
from app.db.models.user import ROLE_ADMIN, ROLE_USER, User
from app.id_validation import OVERLAY_ID_PATTERN

MIN_PASSWORD_LENGTH = 8


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


def admin_exists(db: Session) -> bool:
    return db.execute(
        select(func.count()).select_from(User).where(User.role == ROLE_ADMIN)
    ).scalar_one() > 0


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
    db.flush()
    return user


def authenticate(db: Session, username: str, password: str) -> User | None:
    """Return the user iff *password* matches and the account is active."""
    user = get_by_username(db, username)
    if user is None or not user.is_active:
        # Still verify against a dummy hash to keep timing roughly uniform.
        verify_password(password, "scrypt$n=16384,r=8,p=1$00$00")
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
    db.flush()
    return user


def delete_user(db: Session, user: User) -> None:
    """Delete a user; FK cascades remove their overlays/teams/presets/reports."""
    db.delete(user)
    db.flush()


def list_users(db: Session) -> list[User]:
    return list(
        db.execute(select(User).order_by(User.username)).scalars().all()
    )
