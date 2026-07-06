"""DB-backed teams and groups.

Groups are the primary unit of team selection. A group is **shared**
(``owner_user_id is None`` — admin-curated, visible once ``is_active``) or
**private** (owned by a user). The virtual "All" group (``group_id is None``)
is every global team ∪ the caller's custom teams. Shared-group members are
global teams in ``team_group_members``; a user's additions to a shared group and
every member of a private group live in ``user_group_teams``.

The board team selectors consume ``group_effective_teams_map`` — the existing
``APP_TEAMS`` map ``{name: {icon, color, text_color}}`` — scoped to one group.
The legacy flat-roster helpers (``user_teams``/``*_team_to_user``) remain for
back-compat with the deprecated ``/teams`` and ``/teams/mine`` routes.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.api.schemas import is_acceptable_catalog_icon
from app.db.models.team import (
    Team,
    TeamGroup,
    TeamGroupMember,
    UserGroupTeam,
    UserTeamListItem,
)

# APP_TEAMS sub-keys (mirror app.customization.TEAM_VALUES_*).
ICON = "icon"
COLOR = "color"
TEXT_COLOR = "text_color"

# Name of the private group each user is seeded with (and that the 0007
# migration creates from the legacy flat roster). Must match the migration.
MY_TEAMS_NAME = "My teams"


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
    # ``.first()`` (not ``scalar_one_or_none``) is deliberate: there is no DB
    # uniqueness on global team name, so a concurrent double-insert must not
    # turn every later lookup into a MultipleResultsFound 500.
    return db.execute(
        select(Team).where(Team.is_global.is_(True), Team.name == name)
    ).scalars().first()


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


def update_global(
    db: Session,
    team_id: int,
    *,
    name: str | None = None,
    icon: str | None = None,
    color: str | None = None,
    text_color: str | None = None,
) -> Team:
    """Edit a global team's fields by id. Only provided fields change."""
    team = db.get(Team, team_id)
    if team is None or not team.is_global:
        raise TeamError("Team not found.")
    if name is not None:
        name = name.strip()
        if not name:
            raise TeamError("Team name is required.")
        team.name = name
    if icon is not None:
        team.icon_url = icon or None
    if color is not None:
        team.color = color or None
    if text_color is not None:
        team.text_color = text_color or None
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
        icon = cfg.get(ICON)
        # A dangerous icon scheme nulls just that field instead of
        # failing the whole import — bulk JSON pastes shouldn't die on
        # one bad entry, and the strict customization gate still stands
        # between any stored value and an overlay <img>.
        if icon is not None and not is_acceptable_catalog_icon(icon):
            icon = None
        upsert_global(
            db, name,
            icon=icon, color=cfg.get(COLOR), text_color=cfg.get(TEXT_COLOR),
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


def get_shared_group(db: Session, group_id: int) -> TeamGroup | None:
    """Return the SHARED (admin-curated, ``owner_user_id IS NULL``) group with
    *group_id*, or None. Admin group mutations must resolve groups through this
    so they can never reach a user's *private* group by guessing its id — read
    paths are already owner-scoped, this closes the matching write-path gap."""
    group = db.get(TeamGroup, group_id)
    if group is None or group.owner_user_id is not None:
        return None
    return group


def set_group_active(db: Session, group_id: int, active: bool) -> TeamGroup:
    group = get_shared_group(db, group_id)
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
    """Published SHARED groups (admin-curated). Private groups are excluded —
    they carry ``is_active=True`` but must only ever surface to their owner."""
    return list(
        db.execute(
            select(TeamGroup)
            .where(TeamGroup.is_active.is_(True), TeamGroup.owner_user_id.is_(None))
            .order_by(TeamGroup.name)
        ).scalars().all()
    )


def list_all_groups(db: Session) -> list[TeamGroup]:
    """Every SHARED group, active or not — for the admin group manager. Scoped
    to ``owner_user_id IS NULL`` so a user's private groups never leak here."""
    return list(
        db.execute(
            select(TeamGroup)
            .where(TeamGroup.owner_user_id.is_(None))
            .order_by(TeamGroup.name)
        ).scalars().all()
    )


def remove_group_member(db: Session, group_id: int, team_id: int) -> bool:
    """Unlink a team from a group (idempotent). Returns True if a row was removed."""
    member = db.execute(
        select(TeamGroupMember).where(
            TeamGroupMember.group_id == group_id, TeamGroupMember.team_id == team_id,
        )
    ).scalar_one_or_none()
    if member is None:
        return False
    db.delete(member)
    db.flush()
    return True


def delete_group(db: Session, group_id: int) -> bool:
    """Delete a SHARED group and its membership rows (idempotent). Member teams
    stay in the catalog and in any user list they were already copied into.
    Private (user-owned) groups are never reachable here — use
    :func:`delete_private_group`."""
    group = get_shared_group(db, group_id)
    if group is None:
        return False
    for member in db.execute(
        select(TeamGroupMember).where(TeamGroupMember.group_id == group_id)
    ).scalars().all():
        db.delete(member)
    db.delete(group)
    db.flush()
    return True


def group_member_teams(db: Session, group_id: int) -> list[Team]:
    # is_global filter is defence-in-depth: the add-member route already rejects
    # non-global teams, so any non-global membership row is stale/bad data and
    # must never be surfaced (it would otherwise be copied into user rosters).
    return list(
        db.execute(
            select(Team)
            .join(TeamGroupMember, TeamGroupMember.team_id == Team.id)
            .where(TeamGroupMember.group_id == group_id, Team.is_global.is_(True))
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
    """Add several catalog teams to the user's list in one batch (idempotent).

    Three queries total (validate ids, find existing links, current max
    sort order) instead of three per team.
    """
    ids = list(dict.fromkeys(team_ids))
    if not ids:
        return 0
    found = set(
        db.execute(select(Team.id).where(Team.id.in_(ids))).scalars().all()
    )
    missing = [tid for tid in ids if tid not in found]
    if missing:
        raise TeamError("Team not found.")
    linked = set(
        db.execute(
            select(UserTeamListItem.team_id).where(
                UserTeamListItem.user_id == user_id,
                UserTeamListItem.team_id.in_(ids),
            )
        ).scalars().all()
    )
    to_add = [tid for tid in ids if tid not in linked]
    if not to_add:
        return 0
    sort_order = _next_sort_order(db, user_id)
    for offset, tid in enumerate(to_add):
        db.add(UserTeamListItem(
            user_id=user_id, team_id=tid, sort_order=sort_order + offset,
        ))
    db.flush()
    return len(to_add)


def remove_team_from_user(db: Session, user_id: int, team_id: int) -> bool:
    row = db.execute(
        select(UserTeamListItem).where(
            UserTeamListItem.user_id == user_id, UserTeamListItem.team_id == team_id,
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    team = db.get(Team, team_id)
    # A user's custom team only exists inside their list — removing it deletes
    # it outright (the FK cascade drops the list item). A global team is just
    # unlinked from the list and stays in the admin catalog.
    if team is not None and not team.is_global and team.owner_user_id == user_id:
        db.delete(team)
    else:
        db.delete(row)
    db.flush()
    return True


def remove_teams_from_user(db: Session, user_id: int, team_ids: list[int]) -> int:
    """Remove several teams from the user's list (idempotent). Returns the count."""
    return sum(1 for tid in team_ids if remove_team_from_user(db, user_id, tid))


def seed_user_with_global_teams(db: Session, user_id: int) -> int:
    """Copy every current global team into a user's list. Returns the count.

    Called once at account creation so a new user starts with the full admin
    catalog; later-added global teams are not auto-pushed (the user adds those
    from the catalog).
    """
    return add_teams_to_user(db, user_id, [t.id for t in list_global(db)])


# ---- custom (user-owned) teams ---------------------------------------------


def create_user_team(
    db: Session,
    user_id: int,
    name: str,
    *,
    icon: str | None = None,
    color: str | None = None,
    text_color: str | None = None,
) -> Team:
    """Create a personal (user-owned) team and add it to the user's list."""
    name = (name or "").strip()
    if not name:
        raise TeamError("Team name is required.")
    team = Team(
        name=name,
        is_global=False,
        owner_user_id=user_id,
        icon_url=(icon or "").strip() or None,
        color=(color or "").strip() or None,
        text_color=(text_color or "").strip() or None,
    )
    db.add(team)
    db.flush()
    db.add(UserTeamListItem(
        user_id=user_id, team_id=team.id, sort_order=_next_sort_order(db, user_id),
    ))
    db.flush()
    return team


def update_user_team(
    db: Session,
    user_id: int,
    team_id: int,
    *,
    name: str | None = None,
    icon: str | None = None,
    color: str | None = None,
    text_color: str | None = None,
) -> Team:
    """Edit one of the caller's custom teams. Only provided fields change."""
    team = db.get(Team, team_id)
    if team is None or team.is_global or team.owner_user_id != user_id:
        raise TeamError("Team not found.")
    if name is not None:
        name = name.strip()
        if not name:
            raise TeamError("Team name is required.")
        team.name = name
    if icon is not None:
        team.icon_url = icon.strip() or None
    if color is not None:
        team.color = color.strip() or None
    if text_color is not None:
        team.text_color = text_color.strip() or None
    db.flush()
    return team


def copy_group_to_user(db: Session, user_id: int, group_id: int) -> int:
    """Copy every team in a SHARED active *group_id* into the user's list
    (idempotent). Private groups are not copyable through this legacy path."""
    group = db.get(TeamGroup, group_id)
    if group is None or group.owner_user_id is not None or not group.is_active:
        raise TeamError("Group not found.")
    team_ids = [t.id for t in group_member_teams(db, group_id)]
    return add_teams_to_user(db, user_id, team_ids)


# ---- groups as the primary selection unit ----------------------------------
# A group is SHARED (owner_user_id is None, gated by is_active) or PRIVATE
# (owner_user_id set, visible only to its owner). Per-user membership — a user's
# additions to a shared group and every member of a private group — lives in
# ``UserGroupTeam``. The virtual "All" group (group_id None) is the user's whole
# universe: every global team ∪ the user's own custom teams.


def list_user_custom_teams(db: Session, user_id: int) -> list[Team]:
    """The user's own custom (non-global) teams, ordered by name."""
    return list(
        db.execute(
            select(Team)
            .where(Team.is_global.is_(False), Team.owner_user_id == user_id)
            .order_by(Team.name)
        ).scalars().all()
    )


def list_user_private_groups(db: Session, user_id: int) -> list[TeamGroup]:
    return list(
        db.execute(
            select(TeamGroup)
            .where(TeamGroup.owner_user_id == user_id)
            .order_by(TeamGroup.name)
        ).scalars().all()
    )


def list_user_visible_groups(db: Session, user_id: int) -> list[TeamGroup]:
    """Real groups the user may select: shared+active first, then own private,
    each ordered by name. The synthetic "All" group is added by the caller."""
    return list(
        db.execute(
            select(TeamGroup)
            .where(
                or_(
                    and_(TeamGroup.owner_user_id.is_(None), TeamGroup.is_active.is_(True)),
                    TeamGroup.owner_user_id == user_id,
                )
            )
            # Shared (owner NULL → 0) before private (→ 1), then by name.
            .order_by(TeamGroup.owner_user_id.isnot(None), TeamGroup.name)
        ).scalars().all()
    )


def get_visible_group(db: Session, user_id: int, group_id: int) -> TeamGroup | None:
    """The group if visible to *user_id* (shared+active OR private+owned)."""
    group = db.get(TeamGroup, group_id)
    if group is None:
        return None
    if group.owner_user_id is None:
        return group if group.is_active else None
    return group if group.owner_user_id == user_id else None


def group_kind(group: TeamGroup | None) -> str:
    """``'all'`` (None), ``'private'`` (owned) or ``'shared'`` (admin)."""
    if group is None:
        return "all"
    return "private" if group.owner_user_id is not None else "shared"


def user_group_team_ids(db: Session, user_id: int, group_id: int) -> set[int]:
    """Team ids the user added to *group_id* themselves (their ``UserGroupTeam``
    rows) — i.e. exactly the members they are allowed to remove. Admin-intrinsic
    members of a shared group are not included."""
    return {t.id for t in _user_group_member_teams(db, user_id, group_id)}


def _user_group_member_teams(db: Session, user_id: int, group_id: int) -> list[Team]:
    """Teams the user added to *group_id* via ``UserGroupTeam`` — legitimacy
    filtered (a team must be global or owned by the user)."""
    rows = db.execute(
        select(Team)
        .join(UserGroupTeam, UserGroupTeam.team_id == Team.id)
        .where(UserGroupTeam.user_id == user_id, UserGroupTeam.group_id == group_id)
        .order_by(UserGroupTeam.sort_order, Team.name)
    ).scalars().all()
    return [t for t in rows if t.is_global or t.owner_user_id == user_id]


def group_effective_teams(db: Session, user_id: int, group_id: int | None) -> list[Team]:
    """The teams a user sees for a group. ``group_id is None`` = the "All" group
    (every global ∪ the user's customs). Raises ``TeamError`` if a real group is
    not visible to the user."""
    if group_id is None:
        return list(
            db.execute(
                select(Team)
                .where(or_(Team.is_global.is_(True), Team.owner_user_id == user_id))
                .order_by(Team.name)
            ).scalars().all()
        )
    group = get_visible_group(db, user_id, group_id)
    if group is None:
        raise TeamError("Group not found.")
    teams: dict[int, Team] = {}
    if group.owner_user_id is None:  # shared: admin's global members first
        for team in group_member_teams(db, group_id):
            teams[team.id] = team
    for team in _user_group_member_teams(db, user_id, group_id):  # user additions
        teams[team.id] = team
    return sorted(teams.values(), key=lambda t: t.name.lower())


def group_effective_teams_map(
    db: Session, user_id: int, group_id: int | None,
) -> dict[str, dict[str, Any]]:
    """``group_effective_teams`` in the APP_TEAMS wire shape consumed by the
    board's ``TeamCard`` selectors."""
    return {t.name: team_to_entry(t) for t in group_effective_teams(db, user_id, group_id)}


def create_private_group(db: Session, user_id: int, name: str) -> TeamGroup:
    name = (name or "").strip()
    if not name:
        raise TeamError("Group name is required.")
    group = TeamGroup(
        name=name, is_active=True, owner_user_id=user_id, created_by_user_id=user_id,
    )
    db.add(group)
    db.flush()
    return group


def rename_private_group(db: Session, user_id: int, group_id: int, name: str) -> TeamGroup:
    group = db.get(TeamGroup, group_id)
    if group is None or group.owner_user_id != user_id:
        raise TeamError("Group not found.")
    name = (name or "").strip()
    if not name:
        raise TeamError("Group name is required.")
    group.name = name
    db.flush()
    return group


def delete_private_group(db: Session, user_id: int, group_id: int) -> bool:
    """Delete a private group the user owns (idempotent). Removes its
    ``UserGroupTeam`` rows; the underlying teams stay in the catalog / customs."""
    group = db.get(TeamGroup, group_id)
    if group is None or group.owner_user_id != user_id:
        return False
    for row in db.execute(
        select(UserGroupTeam).where(UserGroupTeam.group_id == group_id)
    ).scalars().all():
        db.delete(row)
    db.delete(group)
    db.flush()
    return True


def _next_group_sort_order(db: Session, user_id: int, group_id: int) -> int:
    current = db.execute(
        select(func.coalesce(func.max(UserGroupTeam.sort_order), -1)).where(
            UserGroupTeam.user_id == user_id, UserGroupTeam.group_id == group_id,
        )
    ).scalar_one()
    return int(current) + 1


def add_user_group_team(db: Session, user_id: int, group_id: int, team_id: int) -> bool:
    """Add a team to a group as a per-user membership (idempotent).

    The group must be visible to the user (shared+active or private+owned) and
    the team must be global or a custom team the user owns. Returns True if a
    row was added. Raises ``TeamError`` on validation failure.
    """
    if get_visible_group(db, user_id, group_id) is None:
        raise TeamError("Group not found.")
    team = db.get(Team, team_id)
    if team is None or not (team.is_global or team.owner_user_id == user_id):
        raise TeamError("Team not found.")
    exists = db.execute(
        select(UserGroupTeam).where(
            UserGroupTeam.user_id == user_id,
            UserGroupTeam.group_id == group_id,
            UserGroupTeam.team_id == team_id,
        )
    ).scalar_one_or_none()
    if exists is not None:
        return False
    db.add(UserGroupTeam(
        user_id=user_id, group_id=group_id, team_id=team_id,
        sort_order=_next_group_sort_order(db, user_id, group_id),
    ))
    db.flush()
    return True


def add_user_group_teams(
    db: Session, user_id: int, group_id: int, team_ids: list[int],
) -> int:
    """Add several teams to a group in one batch (idempotent). Returns the
    count added. Group and teams are each validated with a single query."""
    if get_visible_group(db, user_id, group_id) is None:
        raise TeamError("Group not found.")
    ids = list(dict.fromkeys(team_ids))
    if not ids:
        return 0
    visible = set(
        db.execute(
            select(Team.id).where(
                Team.id.in_(ids),
                or_(Team.is_global.is_(True), Team.owner_user_id == user_id),
            )
        ).scalars().all()
    )
    if any(tid not in visible for tid in ids):
        raise TeamError("Team not found.")
    member = set(
        db.execute(
            select(UserGroupTeam.team_id).where(
                UserGroupTeam.user_id == user_id,
                UserGroupTeam.group_id == group_id,
                UserGroupTeam.team_id.in_(ids),
            )
        ).scalars().all()
    )
    to_add = [tid for tid in ids if tid not in member]
    if not to_add:
        return 0
    sort_order = _next_group_sort_order(db, user_id, group_id)
    for offset, tid in enumerate(to_add):
        db.add(UserGroupTeam(
            user_id=user_id, group_id=group_id, team_id=tid,
            sort_order=sort_order + offset,
        ))
    db.flush()
    return len(to_add)


def remove_user_group_team(db: Session, user_id: int, group_id: int, team_id: int) -> bool:
    """Remove a per-user membership row (idempotent). NEVER deletes the team —
    only its membership in this group for this user."""
    row = db.execute(
        select(UserGroupTeam).where(
            UserGroupTeam.user_id == user_id,
            UserGroupTeam.group_id == group_id,
            UserGroupTeam.team_id == team_id,
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    db.delete(row)
    db.flush()
    return True


def seed_user_default_group(db: Session, user_id: int) -> int:
    """Seed a new account with a private "My teams" group containing every
    current global team (mirrors the 0007 migration for existing users).
    Returns the number of teams added."""
    group = create_private_group(db, user_id, MY_TEAMS_NAME)
    globals_ = list_global(db)
    for index, team in enumerate(globals_):
        db.add(UserGroupTeam(
            user_id=user_id, group_id=group.id, team_id=team.id, sort_order=index,
        ))
    db.flush()
    return len(globals_)
