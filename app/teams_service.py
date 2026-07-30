"""DB-backed teams and groups.

Groups are the primary unit of team selection. A group is **shared**
(``owner_user_id is None`` — admin-curated, visible once ``is_active``) or
**private** (owned by a user). The virtual "All" group (``group_id is None``)
is every global team ∪ the caller's custom teams. Shared-group members are
global teams in ``team_group_members``; a user's additions to a shared group and
every member of a private group live in ``user_group_teams``.

The board team selectors consume ``group_effective_teams_map`` — the existing
``APP_TEAMS`` map ``{name: {icon, color, text_color}}`` — scoped to one group.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.api.schemas import is_acceptable_catalog_icon
from app.db.models.team import Team, TeamGroup, TeamGroupMember, UserGroupTeam
from app.service_errors import (
    NotFoundServiceError,
    ServiceError,
    UnprocessableServiceError,
)

# APP_TEAMS sub-keys (mirror app.customization.TEAM_VALUES_*).
ICON = "icon"
COLOR = "color"
TEXT_COLOR = "text_color"

# Name of the private group each new account is seeded with. Migration 0004
# copies the legacy flat roster into the group with this name, so the two must
# agree — ``tests/test_db_migrations.py`` pins them together.
MY_TEAMS_NAME = "My teams"
ALL_GROUP_NAME = "All teams"


class TeamError(ServiceError):
    """A caller-fixable team error (duplicate, missing, invalid)."""


class TeamNotFoundError(TeamError, NotFoundServiceError):
    """A team or group is not visible in the caller's scope."""

    status_code = 404


class TeamKeyError(TeamError, UnprocessableServiceError):
    """A board group key cannot be parsed."""

    status_code = 422


def team_to_entry(team: Team) -> dict[str, Any]:
    return {ICON: team.icon_url or "", COLOR: team.color or "", TEXT_COLOR: team.text_color or ""}


# ---- global catalog --------------------------------------------------------


def _paged(stmt, limit: int | None, offset: int):
    """Push a ``limit``/``offset`` window into *stmt*; ``limit=None`` = all."""
    if offset:
        stmt = stmt.offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
    return stmt


def list_global(
    db: Session, *, limit: int | None = None, offset: int = 0,
) -> list[Team]:
    return list(
        db.execute(
            _paged(
                select(Team)
                .where(Team.is_global.is_(True))
                # ``name`` is not unique (see get_global_by_name), so the id
                # tiebreaker is what makes a paged walk stable: without it the
                # database may order tied rows differently per query and a
                # client would see some twice and miss others.
                .order_by(Team.name, Team.id),
                limit, offset,
            )
        ).scalars().all()
    )


def count_global(db: Session) -> int:
    return int(
        db.execute(
            select(func.count()).select_from(Team).where(Team.is_global.is_(True))
        ).scalar_one()
    )


def global_catalog(db: Session) -> dict[str, dict[str, Any]]:
    return {t.name: team_to_entry(t) for t in list_global(db)}


def get_global_by_name(db: Session, name: str) -> Team | None:
    # ``.first()`` (not ``scalar_one_or_none``) is deliberate: there is no DB
    # uniqueness on global team name, so a concurrent double-insert must not
    # turn every later lookup into a MultipleResultsFound 500.
    return db.execute(select(Team).where(Team.is_global.is_(True), Team.name == name)).scalars().first()


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
        raise TeamNotFoundError("Team not found.")
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
            db,
            name,
            icon=icon,
            color=cfg.get(COLOR),
            text_color=cfg.get(TEXT_COLOR),
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
        raise TeamNotFoundError("Group not found.")
    group.is_active = active
    db.flush()
    return group


def add_group_member(db: Session, group_id: int, team_id: int) -> None:
    exists = db.execute(
        select(TeamGroupMember).where(
            TeamGroupMember.group_id == group_id,
            TeamGroupMember.team_id == team_id,
        )
    ).scalar_one_or_none()
    if exists is None:
        db.add(TeamGroupMember(group_id=group_id, team_id=team_id))
        db.flush()


def list_all_groups(
    db: Session, *, limit: int | None = None, offset: int = 0,
) -> list[TeamGroup]:
    """Every SHARED group, active or not — for the admin group manager. Scoped
    to ``owner_user_id IS NULL`` so a user's private groups never leak here."""
    return list(
        db.execute(
            _paged(
                select(TeamGroup)
                .where(TeamGroup.owner_user_id.is_(None))
                .order_by(TeamGroup.name, TeamGroup.id),
                limit, offset,
            )
        ).scalars().all()
    )


def count_all_groups(db: Session) -> int:
    return int(
        db.execute(
            select(func.count())
            .select_from(TeamGroup)
            .where(TeamGroup.owner_user_id.is_(None))
        ).scalar_one()
    )


def remove_group_member(db: Session, group_id: int, team_id: int) -> bool:
    """Unlink a team from a group (idempotent). Returns True if a row was removed."""
    member = db.execute(
        select(TeamGroupMember).where(
            TeamGroupMember.group_id == group_id,
            TeamGroupMember.team_id == team_id,
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
    for member in db.execute(select(TeamGroupMember).where(TeamGroupMember.group_id == group_id)).scalars().all():
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
            .order_by(Team.name, Team.id)
        ).scalars().all()
    )


def group_member_teams_bulk(
    db: Session, group_ids: Sequence[int],
) -> dict[int, list[Team]]:
    """:func:`group_member_teams` for many groups in **one** query.

    Returns a dict keyed by group id; ids with no members are present with an
    empty list, so callers never have to branch on a missing key.
    """
    out: dict[int, list[Team]] = {gid: [] for gid in group_ids}
    if not out:
        return out
    rows = db.execute(
        select(TeamGroupMember.group_id, Team)
        .join(Team, TeamGroupMember.team_id == Team.id)
        .where(TeamGroupMember.group_id.in_(list(out)), Team.is_global.is_(True))
        .order_by(TeamGroupMember.group_id, Team.name, Team.id)
    ).all()
    for group_id, team in rows:
        out[group_id].append(team)
    return out


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
    """Create a personal (user-owned) team.

    Ownership alone makes it visible: the virtual "All" group is every global
    team ∪ the caller's customs, so a new team needs no membership row. Add it
    to a group with :func:`add_user_group_team`.
    """
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
        raise TeamNotFoundError("Team not found.")
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


def delete_user_team(db: Session, user_id: int, team_id: int) -> bool:
    """Delete one of the caller's custom teams outright. Returns False when
    *team_id* is not a custom team they own (a global team belongs to the admin
    catalog; drop it from a group with :func:`remove_user_group_team` instead).

    Group memberships referencing it go with it via the ``ON DELETE CASCADE``
    on ``user_group_teams.team_id`` / ``team_group_members.team_id``.
    """
    team = db.get(Team, team_id)
    if team is None or team.is_global or team.owner_user_id != user_id:
        return False
    db.delete(team)
    db.flush()
    return True


# ---- groups as the primary selection unit ----------------------------------
# A group is SHARED (owner_user_id is None, gated by is_active) or PRIVATE
# (owner_user_id set, visible only to its owner). Per-user membership — a user's
# additions to a shared group and every member of a private group — lives in
# ``UserGroupTeam``. The virtual "All" group (group_id None) is the user's whole
# universe: every global team ∪ the user's own custom teams.


def list_user_private_groups(db: Session, user_id: int) -> list[TeamGroup]:
    return list(
        db.execute(select(TeamGroup).where(TeamGroup.owner_user_id == user_id).order_by(TeamGroup.name)).scalars().all()
    )


def _visible_groups_where(user_id: int):
    return or_(
        and_(TeamGroup.owner_user_id.is_(None), TeamGroup.is_active.is_(True)),
        TeamGroup.owner_user_id == user_id,
    )


def list_user_visible_groups(
    db: Session, user_id: int, *, limit: int | None = None, offset: int = 0,
) -> list[TeamGroup]:
    """Real groups the user may select: shared+active first, then own private,
    each ordered by name. The synthetic "All" group is added by the caller."""
    return list(
        db.execute(
            _paged(
                select(TeamGroup)
                .where(_visible_groups_where(user_id))
                # Shared (owner NULL → 0) before private (→ 1), then by name,
                # then id so a paged walk cannot repeat or skip a tied name.
                .order_by(
                    TeamGroup.owner_user_id.isnot(None), TeamGroup.name, TeamGroup.id,
                ),
                limit, offset,
            )
        ).scalars().all()
    )


def count_user_visible_groups(db: Session, user_id: int) -> int:
    return int(
        db.execute(
            select(func.count())
            .select_from(TeamGroup)
            .where(_visible_groups_where(user_id))
        ).scalar_one()
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


def user_group_teams_bulk(
    db: Session, user_id: int, group_ids: Sequence[int],
) -> dict[int, list[Team]]:
    """:func:`_user_group_member_teams` for many groups in **one** query.

    The legitimacy filter (a team must be global or owned by the user) is
    pushed into SQL rather than applied in Python, so a user with a large
    ``UserGroupTeam`` set does not drag rows across the wire just to discard
    them. Every requested id is present in the result, possibly empty.
    """
    out: dict[int, list[Team]] = {gid: [] for gid in group_ids}
    if not out:
        return out
    rows = db.execute(
        select(UserGroupTeam.group_id, Team)
        .join(Team, UserGroupTeam.team_id == Team.id)
        .where(
            UserGroupTeam.user_id == user_id,
            UserGroupTeam.group_id.in_(list(out)),
            or_(Team.is_global.is_(True), Team.owner_user_id == user_id),
        )
        .order_by(UserGroupTeam.group_id, UserGroupTeam.sort_order, Team.name, Team.id)
    ).all()
    for group_id, team in rows:
        out[group_id].append(team)
    return out


def _user_group_member_teams(db: Session, user_id: int, group_id: int) -> list[Team]:
    """Teams the user added to *group_id* via ``UserGroupTeam`` — legitimacy
    filtered (a team must be global or owned by the user)."""
    return user_group_teams_bulk(db, user_id, [group_id])[group_id]


def all_group_teams(
    db: Session, user_id: int, *, limit: int | None = None, offset: int = 0,
) -> list[Team]:
    """The synthetic "All" group: every global team ∪ the user's own customs."""
    return list(
        db.execute(
            _paged(
                select(Team)
                .where(or_(Team.is_global.is_(True), Team.owner_user_id == user_id))
                .order_by(Team.name, Team.id),
                limit, offset,
            )
        ).scalars().all()
    )


def all_group_team_count(db: Session, user_id: int) -> int:
    """``len(all_group_teams(...))`` without materialising a single row."""
    return int(
        db.execute(
            select(func.count())
            .select_from(Team)
            .where(or_(Team.is_global.is_(True), Team.owner_user_id == user_id))
        ).scalar_one()
    )


def group_effective_teams_bulk(
    db: Session, user_id: int, groups: Sequence[TeamGroup],
    *, user_additions: dict[int, list[Team]] | None = None,
) -> dict[int, list[Team]]:
    """:func:`group_effective_teams` for many groups in **two** queries total,
    however many groups are passed.

    *groups* must already be visible to *user_id* — pass rows straight from
    :func:`list_user_visible_groups` or :func:`get_visible_group`. This helper
    deliberately does not re-resolve visibility, which is what lets a listing
    avoid one ``get_visible_group`` round-trip per group.

    Pass *user_additions* (a :func:`user_group_teams_bulk` result covering at
    least these ids) when the caller already needs that map for something else
    — e.g. the "which members may I remove?" list — so the listing runs it once
    instead of twice.
    """
    shared = group_member_teams_bulk(
        db, [g.id for g in groups if g.owner_user_id is None],
    )
    mine = (
        user_group_teams_bulk(db, user_id, [g.id for g in groups])
        if user_additions is None
        else user_additions
    )
    out: dict[int, list[Team]] = {}
    for group in groups:
        teams = {t.id: t for t in shared.get(group.id, ())}
        for team in mine.get(group.id, ()):
            teams[team.id] = team
        out[group.id] = sorted(teams.values(), key=lambda t: t.name.lower())
    return out


def group_effective_counts(
    db: Session, user_id: int, groups: Sequence[TeamGroup],
) -> dict[int, int]:
    """``len(group_effective_teams(...))`` for many groups in **one** query,
    without materialising any ``Team`` row.

    The two membership sources are ``UNION``-ed (not ``UNION ALL``) so a team
    that is both an admin-intrinsic member of a shared group *and* a user
    addition to it counts once — matching the de-duplication
    :func:`group_effective_teams_bulk` does in Python.
    """
    out: dict[int, int] = {g.id: 0 for g in groups}
    if not out:
        return out
    mine = (
        select(
            UserGroupTeam.group_id.label("group_id"),
            UserGroupTeam.team_id.label("team_id"),
        )
        .join(Team, UserGroupTeam.team_id == Team.id)
        .where(
            UserGroupTeam.user_id == user_id,
            UserGroupTeam.group_id.in_(list(out)),
            or_(Team.is_global.is_(True), Team.owner_user_id == user_id),
        )
    )
    shared_ids = [g.id for g in groups if g.owner_user_id is None]
    if shared_ids:
        shared = (
            select(
                TeamGroupMember.group_id.label("group_id"),
                TeamGroupMember.team_id.label("team_id"),
            )
            .join(Team, TeamGroupMember.team_id == Team.id)
            .where(TeamGroupMember.group_id.in_(shared_ids), Team.is_global.is_(True))
        )
        membership = shared.union(mine).subquery()
    else:
        membership = mine.subquery()
    for group_id, count in db.execute(
        select(membership.c.group_id, func.count()).group_by(membership.c.group_id)
    ).all():
        out[group_id] = int(count)
    return out


def group_effective_teams(db: Session, user_id: int, group_id: int | None) -> list[Team]:
    """The teams a user sees for a group. ``group_id is None`` = the "All" group
    (every global ∪ the user's customs). Raises ``TeamError`` if a real group is
    not visible to the user."""
    if group_id is None:
        return all_group_teams(db, user_id)
    group = get_visible_group(db, user_id, group_id)
    if group is None:
        raise TeamNotFoundError("Group not found.")
    return group_effective_teams_bulk(db, user_id, [group])[group_id]


def group_effective_teams_map(
    db: Session,
    user_id: int,
    group_id: int | None,
) -> dict[str, dict[str, Any]]:
    """``group_effective_teams`` in the APP_TEAMS wire shape consumed by the
    board's ``TeamCard`` selectors."""
    return {t.name: team_to_entry(t) for t in group_effective_teams(db, user_id, group_id)}


def create_private_group(db: Session, user_id: int, name: str) -> TeamGroup:
    name = (name or "").strip()
    if not name:
        raise TeamError("Group name is required.")
    group = TeamGroup(
        name=name,
        is_active=True,
        owner_user_id=user_id,
        created_by_user_id=user_id,
    )
    db.add(group)
    db.flush()
    return group


def rename_private_group(db: Session, user_id: int, group_id: int, name: str) -> TeamGroup:
    group = db.get(TeamGroup, group_id)
    if group is None or group.owner_user_id != user_id:
        raise TeamNotFoundError("Group not found.")
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
    for row in db.execute(select(UserGroupTeam).where(UserGroupTeam.group_id == group_id)).scalars().all():
        db.delete(row)
    db.delete(group)
    db.flush()
    return True


def _next_group_sort_order(db: Session, user_id: int, group_id: int) -> int:
    current = db.execute(
        select(func.coalesce(func.max(UserGroupTeam.sort_order), -1)).where(
            UserGroupTeam.user_id == user_id,
            UserGroupTeam.group_id == group_id,
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
        raise TeamNotFoundError("Group not found.")
    team = db.get(Team, team_id)
    if team is None or not (team.is_global or team.owner_user_id == user_id):
        raise TeamNotFoundError("Team not found.")
    exists = db.execute(
        select(UserGroupTeam).where(
            UserGroupTeam.user_id == user_id,
            UserGroupTeam.group_id == group_id,
            UserGroupTeam.team_id == team_id,
        )
    ).scalar_one_or_none()
    if exists is not None:
        return False
    db.add(
        UserGroupTeam(
            user_id=user_id,
            group_id=group_id,
            team_id=team_id,
            sort_order=_next_group_sort_order(db, user_id, group_id),
        )
    )
    db.flush()
    return True


def add_user_group_teams(
    db: Session,
    user_id: int,
    group_id: int,
    team_ids: list[int],
) -> int:
    """Add several teams to a group in one batch (idempotent). Returns the
    count added. Group and teams are each validated with a single query."""
    if get_visible_group(db, user_id, group_id) is None:
        raise TeamNotFoundError("Group not found.")
    ids = list(dict.fromkeys(team_ids))
    if not ids:
        return 0
    visible = set(
        db.execute(
            select(Team.id).where(
                Team.id.in_(ids),
                or_(Team.is_global.is_(True), Team.owner_user_id == user_id),
            )
        )
        .scalars()
        .all()
    )
    if any(tid not in visible for tid in ids):
        raise TeamNotFoundError("Team not found.")
    member = set(
        db.execute(
            select(UserGroupTeam.team_id).where(
                UserGroupTeam.user_id == user_id,
                UserGroupTeam.group_id == group_id,
                UserGroupTeam.team_id.in_(ids),
            )
        )
        .scalars()
        .all()
    )
    to_add = [tid for tid in ids if tid not in member]
    if not to_add:
        return 0
    sort_order = _next_group_sort_order(db, user_id, group_id)
    for offset, tid in enumerate(to_add):
        db.add(
            UserGroupTeam(
                user_id=user_id,
                group_id=group_id,
                team_id=tid,
                sort_order=sort_order + offset,
            )
        )
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
        db.add(
            UserGroupTeam(
                user_id=user_id,
                group_id=group.id,
                team_id=team.id,
                sort_order=index,
            )
        )
    db.flush()
    return len(globals_)
