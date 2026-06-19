"""Key/value application settings & bootstrap flags.

Holds operator-toggleable flags whose value must survive restarts and win
over the env seed once set (e.g. ``registration_open``), plus one-shot
bootstrap state (``admin_bootstrap_claimed``).
"""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

# Known setting keys.
SETTING_REGISTRATION_OPEN = "registration_open"
SETTING_ADMIN_BOOTSTRAP_CLAIMED = "admin_bootstrap_claimed"


class Setting(Base, TimestampMixin):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str | None] = mapped_column(String(255))
