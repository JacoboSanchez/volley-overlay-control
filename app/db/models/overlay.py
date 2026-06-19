"""Per-user overlays and their persisted session-level flags.

A user's overlay is identified to the *user* by its ``oid`` (unique only
within that user — two users may both own ``oid="liga"``), and to *OBS*
by an unguessable ``public_token``. The internal store/session key is
``f"{user_id}:{oid}"`` (see ``app.overlay.skey``).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base, TimestampMixin


class UserOverlay(Base, TimestampMixin):
    __tablename__ = "user_overlays"
    __table_args__ = (
        # The rule that lets two users share an oid: unique per (user, oid),
        # not globally on oid.
        UniqueConstraint("user_id", "oid", name="uq_user_overlays_user_id_oid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    oid: Mapped[str] = mapped_column(String(64), nullable=False)
    # Opaque, globally-unique capability token for the public OBS output URL.
    public_token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(120))

    meta: Mapped[OverlaySessionMeta | None] = relationship(
        back_populates="overlay", cascade="all, delete-orphan",
        passive_deletes=True, uselist=False,
    )


class OverlaySessionMeta(Base, TimestampMixin):
    """Small per-overlay session flags (was ``data/session_meta_<hash>.json``)."""

    __tablename__ = "overlay_session_meta"

    overlay_id: Mapped[int] = mapped_column(
        ForeignKey("user_overlays.id", ondelete="CASCADE"), primary_key=True,
    )
    # The flat flags dict produced by ``GameSession.to_meta_dict`` — kept as a
    # single JSON blob so adding a flag never needs a migration.
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    overlay: Mapped[UserOverlay] = relationship(back_populates="meta")
