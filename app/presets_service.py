"""DB-backed customization presets: global (admin-activated) + per-user.

``values`` is the flat customization patch the control panel
deep-merges; ``categories`` is derived via
:mod:`app.api.preset_categories`. Slug uniqueness is per scope
(``scope_key`` = owner id, or 0 for global) so a user's "corner" and a
global "corner" can coexist.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.preset_categories import categories_for_keys, filter_to_known
from app.constants import PRESETS_MAX_NAME_LEN
from app.db.models.preset import SCOPE_GLOBAL, SCOPE_USER, Preset
from app.service_errors import ConflictServiceError, NotFoundServiceError, ServiceError

# A slug is lowercase ASCII alphanumerics plus dashes, beginning and
# ending with an alphanumeric.
_SLUG_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")

# Reserved so a user-saved preset can never be addressed as one of the
# read-only globals the control panel badges as *System*.
SYSTEM_SLUG_PREFIX = "system-"


class PresetError(ServiceError):
    """A caller-fixable preset error (duplicate, empty, missing)."""


class PresetConflictError(PresetError, ConflictServiceError):
    """A preset slug already exists in the requested scope."""

    status_code = 409


class PresetNotFoundError(PresetError, NotFoundServiceError):
    """A preset does not exist in the requested scope."""

    status_code = 404


def slugify(name: str) -> str:
    """Return a URL-safe slug for *name*.

    Lowercase ASCII alphanumerics plus dashes; runs of any other
    character collapse to a single dash; leading and trailing dashes
    trimmed; empty result raises ``ValueError`` so the caller surfaces
    a 400 instead of writing an unaddressable preset. Length is clamped
    to ``PRESETS_MAX_NAME_LEN`` to keep slugs manageable in URLs and
    JSON. Names that resolve to the reserved ``system-`` prefix are
    rejected for the same reason.
    """
    if not isinstance(name, str):
        raise ValueError("Preset name must be a string.")
    cleaned = re.sub(r"[^a-z0-9]+", "-", name.strip().lower())
    cleaned = cleaned[: max(1, PRESETS_MAX_NAME_LEN)].strip("-")
    if not cleaned or _SLUG_PATTERN.match(cleaned) is None:
        raise ValueError(f"Cannot derive a valid slug from {name!r}.")
    if cleaned.startswith(SYSTEM_SLUG_PREFIX):
        raise ValueError(
            f"Preset slug {cleaned!r} uses the reserved "
            f"{SYSTEM_SLUG_PREFIX!r} prefix.",
        )
    return cleaned


def _make(name: str, values: dict, *, scope: str, owner_user_id: int | None,
          is_active: bool) -> Preset:
    cleaned = filter_to_known(values or {})
    if not cleaned:
        raise PresetError("Preset has no recognised customization values.")
    try:
        slug = slugify(name)
    except ValueError as exc:
        raise PresetError(str(exc)) from exc
    return Preset(
        slug=slug,
        name=name.strip(),
        scope=scope,
        owner_user_id=owner_user_id,
        is_active=is_active,
        categories=categories_for_keys(cleaned.keys()),
        values=cleaned,
    )


def _exists(db: Session, owner_user_id: int | None, slug: str) -> Preset | None:
    return db.execute(
        select(Preset).where(
            Preset.scope_key == (owner_user_id or 0), Preset.slug == slug,
        )
    ).scalar_one_or_none()


# ---- per-user --------------------------------------------------------------


def create_user_preset(db: Session, user_id: int, name: str, values: dict) -> Preset:
    preset = _make(name, values, scope=SCOPE_USER, owner_user_id=user_id, is_active=True)
    if _exists(db, user_id, preset.slug) is not None:
        raise PresetConflictError(f"Preset '{name}' already exists.")
    db.add(preset)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise PresetConflictError(f"Preset '{name}' already exists.") from exc
    return preset


def _for_user_where(user_id: int):
    return ((Preset.scope == SCOPE_GLOBAL) & (Preset.is_active.is_(True))) | (
        Preset.owner_user_id == user_id
    )


def list_for_user(
    db: Session, user_id: int, *, limit: int | None = None, offset: int = 0,
) -> list[Preset]:
    """Active global presets + the caller's own, globals first then by name.

    The sort is expressed in SQL (it used to be a Python ``sorted`` over the
    whole result) so ``limit``/``offset`` page a stable, deterministic order
    instead of an arbitrary slice of the unordered rows.
    """
    stmt = (
        select(Preset)
        .where(_for_user_where(user_id))
        # Globals (scope == 'global' → false → 0) before the caller's own.
        .order_by(Preset.scope != SCOPE_GLOBAL, func.lower(Preset.name), Preset.id)
    )
    if offset:
        stmt = stmt.offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(db.execute(stmt).scalars().all())


def count_for_user(db: Session, user_id: int) -> int:
    return int(
        db.execute(
            select(func.count()).select_from(Preset).where(_for_user_where(user_id))
        ).scalar_one()
    )


def get_user_preset(db: Session, user_id: int, slug: str) -> Preset | None:
    preset = _exists(db, user_id, slug)
    return preset if preset is not None and preset.scope == SCOPE_USER else None


def delete_user_preset(db: Session, user_id: int, slug: str) -> bool:
    preset = get_user_preset(db, user_id, slug)
    if preset is None:
        return False
    db.delete(preset)
    db.flush()
    return True


# ---- admin / global --------------------------------------------------------


def create_global_preset(db: Session, name: str, values: dict, *, is_active: bool = True) -> Preset:
    preset = _make(name, values, scope=SCOPE_GLOBAL, owner_user_id=None, is_active=is_active)
    if _exists(db, None, preset.slug) is not None:
        raise PresetConflictError(f"Global preset '{name}' already exists.")
    db.add(preset)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise PresetConflictError(f"Global preset '{name}' already exists.") from exc
    return preset


def get_global_preset(db: Session, slug: str) -> Preset | None:
    preset = _exists(db, None, slug)
    return preset if preset is not None and preset.scope == SCOPE_GLOBAL else None


def set_global_active(db: Session, slug: str, active: bool) -> Preset:
    preset = get_global_preset(db, slug)
    if preset is None:
        raise PresetNotFoundError("Global preset not found.")
    preset.is_active = active
    db.flush()
    return preset


def delete_global_preset(db: Session, slug: str) -> bool:
    preset = get_global_preset(db, slug)
    if preset is None:
        return False
    db.delete(preset)
    db.flush()
    return True


def list_global_presets(
    db: Session, *, limit: int | None = None, offset: int = 0,
) -> list[Preset]:
    stmt = select(Preset).where(Preset.scope == SCOPE_GLOBAL).order_by(Preset.name, Preset.id)
    if offset:
        stmt = stmt.offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(db.execute(stmt).scalars().all())


def count_global_presets(db: Session) -> int:
    return int(
        db.execute(
            select(func.count()).select_from(Preset).where(Preset.scope == SCOPE_GLOBAL)
        ).scalar_one()
    )


def import_app_themes(db: Session, payload: dict, *, replace: bool = False) -> int:
    """Upsert global presets from an ``APP_THEMES`` JSON map. Returns count."""
    if not isinstance(payload, dict):
        raise PresetError("Expected a JSON object of {name: {values...}}.")
    if replace:
        for preset in list_global_presets(db):
            db.delete(preset)
        db.flush()
    count = 0
    for name, raw in payload.items():
        cleaned = filter_to_known(raw if isinstance(raw, dict) else {})
        if not cleaned:
            continue
        existing = None
        try:
            existing = _exists(db, None, slugify(str(name)))
        except ValueError:
            continue
        if existing is not None:
            existing.name = str(name).strip()
            existing.categories = categories_for_keys(cleaned.keys())
            existing.values = cleaned
        else:
            db.add(_make(str(name), cleaned, scope=SCOPE_GLOBAL,
                         owner_user_id=None, is_active=True))
        count += 1
    db.flush()
    return count


def export_app_themes(db: Session) -> dict[str, dict[str, Any]]:
    return {p.name: dict(p.values) for p in list_global_presets(db)}
