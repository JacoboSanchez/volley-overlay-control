"""Teams catalog, admin team-groups, and per-user team lists.

Replaces the env-driven ``APP_TEAMS`` / ``Customization.predefined_teams``.
A team is either global (``is_global=True``, ``owner_user_id=None``) or a
user-owned clone. Admins curate global ``TeamGroup``s (e.g. "Liga Gallega");
a user copies a group's members into their personal ``UserTeamListItem`` list.
"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Team(Base, TimestampMixin):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    icon_url: Mapped[str | None] = mapped_column(String(2048))
    color: Mapped[str | None] = mapped_column(String(32))
    text_color: Mapped[str | None] = mapped_column(String(32))
    is_global: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Null for global teams; set for a user-owned team.
    owner_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True,
    )


class TeamGroup(Base, TimestampMixin):
    __tablename__ = "team_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
    )

    members: Mapped[list[TeamGroupMember]] = relationship(
        back_populates="group", cascade="all, delete-orphan", passive_deletes=True,
    )


class TeamGroupMember(Base):
    __tablename__ = "team_group_members"
    __table_args__ = (
        UniqueConstraint("group_id", "team_id", name="uq_team_group_members_group_id_team_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(
        ForeignKey("team_groups.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    team_id: Mapped[int] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True,
    )

    group: Mapped[TeamGroup] = relationship(back_populates="members")


class UserTeamListItem(Base, TimestampMixin):
    __tablename__ = "user_team_list"
    __table_args__ = (
        UniqueConstraint("user_id", "team_id", name="uq_user_team_list_user_id_team_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    team_id: Mapped[int] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
