"""DB-backed customization presets: global (admin-activated) + per-user.

Replaces the on-disk ``presets_store`` and the env-driven ``APP_THEMES``
system presets. ``values`` is the flat customization patch the control
panel deep-merges; ``categories`` is derived via
:mod:`app.api.preset_categories`. Slug uniqueness is per scope
(``scope_key`` = owner id, or 0 for global) so a user's "corner" and a
global "corner" can coexist.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.preset_categories import categories_for_keys, filter_to_known
from app.api.presets_store import slugify
from app.db.models.preset import SCOPE_GLOBAL, SCOPE_USER, Preset


class PresetError(ValueError):
    """A caller-fixable preset error (duplicate, empty, missing)."""


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
        raise PresetError(f"Preset '{name}' already exists.")
    db.add(preset)
    db.flush()
    return preset


def list_for_user(db: Session, user_id: int) -> list[Preset]:
    """Active global presets + the caller's own, globals first then by name."""
    rows = db.execute(
        select(Preset).where(
            ((Preset.scope == SCOPE_GLOBAL) & (Preset.is_active.is_(True)))
            | (Preset.owner_user_id == user_id)
        )
    ).scalars().all()
    return sorted(
        rows, key=lambda p: (p.scope != SCOPE_GLOBAL, p.name.lower()),
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
        raise PresetError(f"Global preset '{name}' already exists.")
    db.add(preset)
    db.flush()
    return preset


def get_global_preset(db: Session, slug: str) -> Preset | None:
    preset = _exists(db, None, slug)
    return preset if preset is not None and preset.scope == SCOPE_GLOBAL else None


def set_global_active(db: Session, slug: str, active: bool) -> Preset:
    preset = get_global_preset(db, slug)
    if preset is None:
        raise PresetError("Global preset not found.")
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


def list_global_presets(db: Session) -> list[Preset]:
    return list(
        db.execute(
            select(Preset).where(Preset.scope == SCOPE_GLOBAL).order_by(Preset.name)
        ).scalars().all()
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
