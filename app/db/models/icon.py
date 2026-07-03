"""Hosted team-icon library.

An icon is an image uploaded to (or imported by) the app, stored on disk
under ``data/media/icons/`` and served from the public ``/media`` mount.
The row carries only metadata; ``filename`` is content-addressed
(``<sha256[:20]>-<random>.webp``) so the public URL
``/media/icons/<filename>`` is immutable and safe to cache forever.

Ownership mirrors :class:`app.db.models.team.Team`: an icon is either
global (``is_global=True``, ``owner_user_id=None`` — admin-managed,
usable by everyone) or personal (``owner_user_id`` set). Teams reference
icons only through their ``icon_url`` string — there is deliberately no
FK, so the whole string pipeline (APP_TEAMS export, board customization,
overlay broadcast) stays unchanged; deletion clears referencing teams by
exact URL match.
"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Icon(Base, TimestampMixin):
    __tablename__ = "icons"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # Unique per row even for identical content (random suffix), so a
    # DELETE can unlink the file unconditionally without refcounting.
    filename: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    mime: Mapped[str] = mapped_column(String(64), nullable=False, default="image/webp")
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    is_global: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Null for global icons; set for a user-owned icon.
    owner_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True,
    )
