"""Per-user overlays and their persisted session-level flags.

A user's overlay is identified to the *user* by its ``oid`` (unique only
within that user — two users may both own ``oid="liga"``), and to *OBS*
by an unguessable ``public_token``. The internal store/session key is
``f"{user_id}:{oid}"`` (see ``app.overlay.skey``).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
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
    # Opaque, globally-unique capability token for the *control* board. Anyone
    # with this token can drive the scoreboard without logging in (a link the
    # owner hands to an operator). Resolves to this overlay's storage key, so it
    # also separates two users sharing the same ``oid``. Nullable only so rows
    # predating the column (backfilled by migration) remain valid; the service
    # always mints one on create. Regenerating it revokes old links.
    control_token: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    # Opt-in: when true, the board can also be controlled — without logging in —
    # from its stable ``/board?u=<username>&oid=<oid>`` URL (a permanent personal
    # bookmark). That URL is *guessable* (username + oid), so it stays off by
    # default; the shareable, revocable control token is the private capability.
    public_control: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default="0",
    )
    display_name: Mapped[str | None] = mapped_column(String(120))
    # Optional per-overlay default match rules applied at session creation, so
    # an overlay's format (best-of-3 vs 5, points) can be configured without
    # opening the board. ``None`` falls back to the env defaults; once the
    # board edits the rules they persist in the session meta and win.
    points: Mapped[int | None] = mapped_column(Integer)
    points_last_set: Mapped[int | None] = mapped_column(Integer)
    sets: Mapped[int | None] = mapped_column(Integer)

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
