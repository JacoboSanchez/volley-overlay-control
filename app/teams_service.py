"""DB-backed teams: global catalog, admin team-groups, per-user lists.

Replaces the env-driven ``APP_TEAMS`` / ``Customization.predefined_teams``.
The wire shape stays the existing ``APP_TEAMS`` map
``{name: {icon, color, text_color}}`` so the control UI (and a
config-provider JSON paste) keep working unchanged.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.team import Team, TeamGroup, TeamGroupMember, UserTeamListItem

# APP_TEAMS sub-keys (mirror app.customization.TEAM_VALUES_*).
ICON = "icon"
COLOR = "color"
TEXT_COLOR = "text_color"


class TeamError(ValueError):
    """A caller-fixable team error (duplicate, missing, invalid)."""


def team_to_entry(team: Team) -> dict[str, Any]:
    return {ICON: team.icon_url or "", COLOR: team.color or "", TEXT_COLOR: team.text_color or ""}


# ---- global catalog --------------------------------------------------------


def list_global(db: Session) -> list[Team]:
    return list(
        db.execute(
            select(Team).where(Team.is_global.is_(True)).order_by(Team.name)
        ).scalars().all()
    )


def global_catalog(db: Session) -> dict[str, dict[str, Any]]:
    return {t.name: team_to_entry(t) for t in list_global(db)}


def get_global_by_name(db: Session, name: str) -> Team | None:
    return db.execute(
        select(Team).where(Team.is_global.is_(True), Team.name == name)
    ).scalar_one_or_none()


def upsert_global(db: Session, name: str, *, icon=None, color=None, text_color=None) -> Team:
    name = (name or "").strip()
    if not name:
        raise TeamError("Team name is required.")
    team = get_global_by_name(db, name)
    if team is None:
        team = Team(name=name, is_global=True)
        db.add(team)
    team.icon_url = icon
    team.color = color
    team.text_color = text_color
    db.flush()
    return team


def delete_global(db: Session, team_id: int) -> bool:
    team = db.get(Team, team_id)
    if team is None or not team.is_global:
        return False
    db.delete(team)
    db.flush()
    return True


def import_app_teams(db: Session, payload: dict, *, replace: bool = False) -> int:
    """Upsert global teams from an ``APP_TEAMS`` map. Returns the count.

    ``replace=True`` first removes every existing global team (and, via FK
    cascade, their group memberships / user-list references).
    """
    if not isinstance(payload, dict):
        raise TeamError("Expected a JSON object of {name: {icon, color, text_color}}.")
    if replace:
        for team in list_global(db):
            db.delete(team)
        db.flush()
    count = 0
    for name, cfg in payload.items():
        cfg = cfg if isinstance(cfg, dict) else {}
        upsert_global(
            db, name,
            icon=cfg.get(ICON), color=cfg.get(COLOR), text_color=cfg.get(TEXT_COLOR),
        )
        count += 1
    return count


def export_app_teams(db: Session) -> dict[str, dict[str, Any]]:
    return global_catalog(db)


# ---- team groups -----------------------------------------------------------


def create_group(db: Session, name: str, *, created_by_user_id: int | None = None) -> TeamGroup:
    name = (name or "").strip()
    if not name:
        raise TeamError("Group name is required.")
    group = TeamGroup(name=name, created_by_user_id=created_by_user_id)
    db.add(group)
    db.flush()
    return group


def set_group_active(db: Session, group_id: int, active: bool) -> TeamGroup:
    group = db.get(TeamGroup, group_id)
    if group is None:
        raise TeamError("Group not found.")
    group.is_active = active
    db.flush()
    return group


def add_group_member(db: Session, group_id: int, team_id: int) -> None:
    exists = db.execute(
        select(TeamGroupMember).where(
            TeamGroupMember.group_id == group_id, TeamGroupMember.team_id == team_id,
        )
    ).scalar_one_or_none()
    if exists is None:
        db.add(TeamGroupMember(group_id=group_id, team_id=team_id))
        db.flush()


def list_active_groups(db: Session) -> list[TeamGroup]:
    return list(
        db.execute(
            select(TeamGroup).where(TeamGroup.is_active.is_(True)).order_by(TeamGroup.name)
        ).scalars().all()
    )


def group_member_teams(db: Session, group_id: int) -> list[Team]:
    return list(
        db.execute(
            select(Team)
            .join(TeamGroupMember, TeamGroupMember.team_id == Team.id)
            .where(TeamGroupMember.group_id == group_id)
            .order_by(Team.name)
        ).scalars().all()
    )


# ---- per-user team list ----------------------------------------------------


def list_user_team_rows(db: Session, user_id: int) -> list[Team]:
    return list(
        db.execute(
            select(Team)
            .join(UserTeamListItem, UserTeamListItem.team_id == Team.id)
            .where(UserTeamListItem.user_id == user_id)
            .order_by(UserTeamListItem.sort_order, Team.name)
        ).scalars().all()
    )


def user_teams(db: Session, user_id: int) -> dict[str, dict[str, Any]]:
    return {t.name: team_to_entry(t) for t in list_user_team_rows(db, user_id)}


def _next_sort_order(db: Session, user_id: int) -> int:
    current = db.execute(
        select(func.coalesce(func.max(UserTeamListItem.sort_order), -1)).where(
            UserTeamListItem.user_id == user_id,
        )
    ).scalar_one()
    return int(current) + 1


def add_team_to_user(db: Session, user_id: int, team_id: int) -> bool:
    """Add a catalog team to the user's list (idempotent). Returns True if added."""
    if db.get(Team, team_id) is None:
        raise TeamError("Team not found.")
    exists = db.execute(
        select(UserTeamListItem).where(
            UserTeamListItem.user_id == user_id, UserTeamListItem.team_id == team_id,
        )
    ).scalar_one_or_none()
    if exists is not None:
        return False
    db.add(UserTeamListItem(
        user_id=user_id, team_id=team_id, sort_order=_next_sort_order(db, user_id),
    ))
    db.flush()
    return True


def add_teams_to_user(db: Session, user_id: int, team_ids: list[int]) -> int:
    added = 0
    for tid in team_ids:
        if add_team_to_user(db, user_id, tid):
            added += 1
    return added


def remove_team_from_user(db: Session, user_id: int, team_id: int) -> bool:
    row = db.execute(
        select(UserTeamListItem).where(
            UserTeamListItem.user_id == user_id, UserTeamListItem.team_id == team_id,
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    db.delete(row)
    db.flush()
    return True


def copy_group_to_user(db: Session, user_id: int, group_id: int) -> int:
    """Copy every team in *group_id* into the user's list (idempotent)."""
    group = db.get(TeamGroup, group_id)
    if group is None or not group.is_active:
        raise TeamError("Group not found.")
    team_ids = [t.id for t in group_member_teams(db, group_id)]
    return add_teams_to_user(db, user_id, team_ids)
