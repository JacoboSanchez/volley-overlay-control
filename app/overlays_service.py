"""Per-user overlay CRUD.

Owns the ``user_overlays`` table: a user identifies an overlay by its
``oid`` (unique only within their account); OBS identifies it by an
unguessable ``public_token``. The internal storage key is
:func:`app.overlay_key.make_skey`.
"""

from __future__ import annotations

import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.overlay import UserOverlay
from app.id_validation import validate_overlay_id
from app.overlay_key import make_skey

_PUBLIC_TOKEN_BYTES = 18  # → 24-char url-safe token


class OverlayError(ValueError):
    """A caller-fixable overlay error (duplicate oid, invalid id, ...)."""


def _generate_token(db: Session, column) -> str:
    """Return a fresh, collision-checked url-safe token unique on *column*."""
    for _ in range(8):
        token = secrets.token_urlsafe(_PUBLIC_TOKEN_BYTES)
        exists = db.execute(select(UserOverlay.id).where(column == token)).first()
        if exists is None:
            return token
    raise OverlayError("Could not allocate a unique overlay token.")  # pragma: no cover


def _generate_public_token(db: Session) -> str:
    """Return a fresh, collision-checked public (OBS output) token."""
    return _generate_token(db, UserOverlay.public_token)


def _generate_control_token(db: Session) -> str:
    """Return a fresh, collision-checked control (shareable board) token."""
    return _generate_token(db, UserOverlay.control_token)


def normalize_oid(raw: str) -> str:
    """Validate and return a bare overlay id (raises :class:`OverlayError`)."""
    try:
        return validate_overlay_id((raw or "").strip())
    except ValueError as exc:
        raise OverlayError(str(exc)) from exc


def create_overlay(
    db: Session,
    user_id: int,
    oid: str,
    *,
    display_name: str | None = None,
    output_url: str | None = None,
    points: int | None = None,
    points_last_set: int | None = None,
    sets: int | None = None,
) -> UserOverlay:
    """Create a ``user_overlays`` row. Raises on duplicate/invalid oid."""
    oid = normalize_oid(oid)
    if get_overlay(db, user_id, oid) is not None:
        raise OverlayError("You already have an overlay with that id.")
    overlay = UserOverlay(
        user_id=user_id,
        oid=oid,
        public_token=_generate_public_token(db),
        control_token=_generate_control_token(db),
        display_name=(display_name or "").strip() or None,
        output_url=(output_url or "").strip() or None,
        points=points,
        points_last_set=points_last_set,
        sets=sets,
    )
    db.add(overlay)
    db.flush()
    return overlay


_UNSET = object()


def update_overlay(
    db: Session,
    user_id: int,
    oid: str,
    *,
    display_name: object = _UNSET,
    output_url: object = _UNSET,
    points: object = _UNSET,
    points_last_set: object = _UNSET,
    sets: object = _UNSET,
) -> UserOverlay:
    """Update an overlay's editable settings. Only provided fields change."""
    overlay = get_overlay(db, user_id, oid)
    if overlay is None:
        raise OverlayError("Overlay not found.")
    if display_name is not _UNSET:
        overlay.display_name = (str(display_name or "").strip()) or None
    if output_url is not _UNSET:
        overlay.output_url = (str(output_url or "").strip()) or None
    if points is not _UNSET:
        overlay.points = points
    if points_last_set is not _UNSET:
        overlay.points_last_set = points_last_set
    if sets is not _UNSET:
        overlay.sets = sets
    db.flush()
    return overlay


def get_overlay(db: Session, user_id: int, oid: str) -> UserOverlay | None:
    return db.execute(
        select(UserOverlay).where(
            UserOverlay.user_id == user_id, UserOverlay.oid == oid,
        )
    ).scalar_one_or_none()


def get_by_public_token(db: Session, token: str) -> UserOverlay | None:
    if not token:
        return None
    return db.execute(
        select(UserOverlay).where(UserOverlay.public_token == token)
    ).scalar_one_or_none()


def get_by_control_token(db: Session, token: str) -> UserOverlay | None:
    """Resolve the overlay a shareable control link points at, or ``None``."""
    if not token:
        return None
    return db.execute(
        select(UserOverlay).where(UserOverlay.control_token == token)
    ).scalar_one_or_none()


def ensure_control_token(db: Session, overlay: UserOverlay) -> str:
    """Return the overlay's control token, minting one if a legacy row lacks it."""
    if not overlay.control_token:
        overlay.control_token = _generate_control_token(db)
        db.flush()
    return overlay.control_token


def regenerate_control_token(db: Session, user_id: int, oid: str) -> UserOverlay:
    """Mint a new control token, revoking any previously-shared link."""
    overlay = get_overlay(db, user_id, oid)
    if overlay is None:
        raise OverlayError("Overlay not found.")
    overlay.control_token = _generate_control_token(db)
    db.flush()
    return overlay


def list_overlays(db: Session, user_id: int) -> list[UserOverlay]:
    return list(
        db.execute(
            select(UserOverlay)
            .where(UserOverlay.user_id == user_id)
            .order_by(UserOverlay.oid)
        ).scalars().all()
    )


def delete_overlay(db: Session, user_id: int, oid: str) -> bool:
    overlay = get_overlay(db, user_id, oid)
    if overlay is None:
        return False
    db.delete(overlay)
    db.flush()
    return True


def skey_for(overlay: UserOverlay) -> str:
    return make_skey(overlay.user_id, overlay.oid)
