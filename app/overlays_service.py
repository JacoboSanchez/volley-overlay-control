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


def _generate_public_token(db: Session) -> str:
    """Return a fresh, collision-checked public token."""
    for _ in range(8):
        token = secrets.token_urlsafe(_PUBLIC_TOKEN_BYTES)
        exists = db.execute(
            select(UserOverlay.id).where(UserOverlay.public_token == token)
        ).first()
        if exists is None:
            return token
    raise OverlayError("Could not allocate a unique overlay token.")  # pragma: no cover


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
) -> UserOverlay:
    """Create a ``user_overlays`` row. Raises on duplicate/invalid oid."""
    oid = normalize_oid(oid)
    if get_overlay(db, user_id, oid) is not None:
        raise OverlayError("You already have an overlay with that id.")
    overlay = UserOverlay(
        user_id=user_id,
        oid=oid,
        public_token=_generate_public_token(db),
        display_name=(display_name or "").strip() or None,
    )
    db.add(overlay)
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
