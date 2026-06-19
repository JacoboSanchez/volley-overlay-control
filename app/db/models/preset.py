"""Customization presets — global (admin-activated) and per-user.

Replaces the on-disk ``data/presets/*.json`` store and the env-driven
``APP_THEMES`` system presets. ``values`` holds the flat customization
key/value map (e.g. ``"Team 1 Color"``, ``"Width"``); ``categories`` the
grouping computed by ``app.api.preset_categories``.

Slug uniqueness must be per-scope (a user's "corner" and a global "corner"
can coexist). ``owner_user_id`` is NULL for global presets, and SQLite
treats NULLs as distinct in a unique index — so a generated ``scope_key``
(``owner_user_id`` coalesced to 0) carries the uniqueness instead. It is
maintained by the ``before_insert``/``before_update`` hooks below.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint, event
from sqlalchemy.orm import Mapped, Mapper, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base, TimestampMixin

SCOPE_GLOBAL = "global"
SCOPE_USER = "user"


class Preset(Base, TimestampMixin):
    __tablename__ = "presets"
    __table_args__ = (
        UniqueConstraint("scope_key", "slug", name="uq_presets_scope_key_slug"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    owner_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True,
    )
    # Derived: owner_user_id or 0. Carries per-scope slug uniqueness without
    # tripping SQLite's "NULLs are distinct" behaviour in the unique index.
    scope_key: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Global presets are visible to all users only when active; user presets
    # are always usable by their owner.
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    categories: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    values: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


@event.listens_for(Preset, "before_insert")
@event.listens_for(Preset, "before_update")
def _sync_scope_key(_mapper: Mapper, _conn: Any, target: Preset) -> None:
    target.scope_key = target.owner_user_id or 0
