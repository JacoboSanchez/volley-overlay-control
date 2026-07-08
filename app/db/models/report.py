"""DB-backed match reports (replaces ``data/matches/*.json`` + ``index.jsonl``).

Mirrors the ``archive_match`` payload shape, plus ``user_id`` for ownership
and account-screen listing. ``match_id`` keeps the historical
``match_<20hex>_<UTC>`` format so ``/match/{id}/report`` parsing and the
HMAC report-signing keep working. Per-set summary numbers are computed from
``final_state`` on read rather than stored (they were the ``index.jsonl``
columns).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base, TimestampMixin


class MatchReport(Base, TimestampMixin):
    __tablename__ = "match_reports"
    __table_args__ = (
        Index("ix_match_reports_user_oid_ended", "user_id", "oid", "ended_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
    )
    oid: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    started_at: Mapped[float | None] = mapped_column(Float)
    ended_at: Mapped[float | None] = mapped_column(Float)
    duration_s: Mapped[float | None] = mapped_column(Float)
    winning_team: Mapped[int | None] = mapped_column(Integer)
    final_state: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    customization: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    audit_log: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    points_limit: Mapped[int | None] = mapped_column(Integer)
    points_limit_last_set: Mapped[int | None] = mapped_column(Integer)
    sets_limit: Mapped[int | None] = mapped_column(Integer)
