"""Application settings backed by the ``settings`` table.

A setting's value, once written by an operator/admin, wins over the env
seed for all subsequent boots ("DB wins after first boot"). When no row
exists yet, the value falls back to the env var and finally a hard default.
This gives ``REGISTRATION_OPEN`` env-seed-then-DB-override semantics without
baking a value into a migration.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.setting import (
    SETTING_ADMIN_BOOTSTRAP_CLAIMED,
    SETTING_REGISTRATION_OPEN,
    Setting,
)
from app.env_vars_manager import EnvVarsManager, is_truthy

_TRUE = "true"
_FALSE = "false"


def _get_raw(db: Session, key: str) -> str | None:
    return db.execute(
        select(Setting.value).where(Setting.key == key)
    ).scalar_one_or_none()


def _set_raw(db: Session, key: str, value: str) -> None:
    row = db.get(Setting, key)
    if row is None:
        db.add(Setting(key=key, value=value))
    else:
        row.value = value
    db.flush()


def _env_seed(env_var: str) -> str | None:
    """The env seed for a setting, treating empty/whitespace as unset.

    docker-compose passes ``VAR=${VAR:-}`` for optional vars, so an empty
    string means "operator did not configure this", not "false".
    """
    raw = EnvVarsManager.get_env_var(env_var, None)
    if raw is None:
        return None
    text = raw if isinstance(raw, str) else str(raw)
    return text if text.strip() else None


def get_bool(db: Session, key: str, *, env_var: str, default: bool) -> bool:
    """Return a boolean setting: DB row → env seed → hard default."""
    raw = _get_raw(db, key)
    if raw is not None:
        return raw == _TRUE
    env_raw = _env_seed(env_var)
    if env_raw is not None:
        return is_truthy(env_raw)
    return default


def set_bool(db: Session, key: str, value: bool) -> None:
    _set_raw(db, key, _TRUE if value else _FALSE)


def registration_open(db: Session) -> bool:
    """Whether public self-registration is currently allowed."""
    return get_bool(
        db, SETTING_REGISTRATION_OPEN, env_var="REGISTRATION_OPEN", default=True,
    )


def set_registration_open(db: Session, value: bool) -> None:
    set_bool(db, SETTING_REGISTRATION_OPEN, value)


def registration_explicitly_configured(db: Session) -> bool:
    """True when an operator pinned registration via a DB row or the env var.

    Used by the first-admin claim to decide whether to auto-close public
    sign-ups: an explicit operator choice (either source) is respected.
    """
    if _get_raw(db, SETTING_REGISTRATION_OPEN) is not None:
        return True
    return _env_seed("REGISTRATION_OPEN") is not None


def admin_bootstrap_claimed(db: Session) -> bool:
    return get_bool(
        db,
        SETTING_ADMIN_BOOTSTRAP_CLAIMED,
        env_var="__never_set__",
        default=False,
    )


def set_admin_bootstrap_claimed(db: Session, value: bool) -> None:
    set_bool(db, SETTING_ADMIN_BOOTSTRAP_CLAIMED, value)
