"""Per-user overlays.

A user's overlay is identified to the *user* by its ``oid`` (unique only
within that user — two users may both own ``oid="liga"``), and to *OBS*
by an unguessable ``public_token``. The internal store/session key is
``f"{user_id}:{oid}"`` (see ``app.overlay.skey``).
"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

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
    # Optional free-text description shown under the overlay's id (its name)
    # in the account UI. Not an alternative name — the ``oid`` is the name.
    description: Mapped[str | None] = mapped_column(String(120))

