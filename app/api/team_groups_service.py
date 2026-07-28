"""Response assembly and board policy for team-group routes."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app import teams_service
from app.api.schemas import (
    BoardGroupListOut,
    BoardGroupOut,
    GroupDetailOut,
    TeamGroupOut,
    TeamOut,
)
from app.api.session_persistence import load_session_meta
from app.constants import LIST_MAX_LIMIT
from app.db.models.team import TeamGroup


def parse_group_key(group_key: str) -> int | None:
    """Return ``None`` for the synthetic All group or parse a real group id."""
    if group_key == "all":
        return None
    try:
        return int(group_key)
    except ValueError as exc:
        raise teams_service.TeamError("Invalid group key.") from exc


def all_group_detail(db: Session, user_id: int) -> GroupDetailOut:
    """Build the bounded embedded representation of the synthetic All group."""
    teams = teams_service.all_group_teams(
        db,
        user_id,
        limit=LIST_MAX_LIMIT,
    )
    return GroupDetailOut(
        id=None,
        name=teams_service.ALL_GROUP_NAME,
        kind="all",
        is_private=False,
        teams=[TeamOut.of(team) for team in teams],
    )


def admin_group_rows(
    db: Session,
    groups: list[TeamGroup],
) -> list[TeamGroupOut]:
    """Build a page of shared groups with one bulk membership query."""
    members = teams_service.group_member_teams_bulk(
        db,
        [group.id for group in groups],
    )
    return [
        TeamGroupOut(
            id=group.id,
            name=group.name,
            is_active=group.is_active,
            teams=[TeamOut.of(team) for team in members[group.id]],
        )
        for group in groups
    ]


def group_details(
    db: Session,
    user_id: int,
    groups: list[TeamGroup],
) -> list[GroupDetailOut]:
    """Build several visible group details at a fixed query cost."""
    additions = teams_service.user_group_teams_bulk(
        db,
        user_id,
        [group.id for group in groups],
    )
    effective = teams_service.group_effective_teams_bulk(
        db,
        user_id,
        groups,
        user_additions=additions,
    )
    return [
        GroupDetailOut(
            id=group.id,
            name=group.name,
            kind=teams_service.group_kind(group),
            is_private=group.owner_user_id is not None,
            teams=[TeamOut.of(team) for team in effective[group.id]],
            removable_ids=sorted(team.id for team in additions[group.id]),
        )
        for group in groups
    ]


def group_detail(
    db: Session,
    user_id: int,
    group: TeamGroup,
) -> GroupDetailOut:
    """Build one visible group detail."""
    return group_details(db, user_id, [group])[0]


def board_group_list(
    db: Session,
    owner_id: int,
    skey: str,
) -> BoardGroupListOut:
    """Build the board picker and validate its persisted selection."""
    visible = teams_service.list_user_visible_groups(db, owner_id)
    counts = teams_service.group_effective_counts(db, owner_id, visible)
    groups = [
        BoardGroupOut(
            id=None,
            name=teams_service.ALL_GROUP_NAME,
            kind="all",
            count=teams_service.all_group_team_count(db, owner_id),
        ),
        *[
            BoardGroupOut(
                id=group.id,
                name=group.name,
                kind=teams_service.group_kind(group),
                count=counts.get(group.id, 0),
            )
            for group in visible
        ],
    ]

    meta = load_session_meta(skey)
    selected = (
        meta.get("selected_team_group_id")
        if isinstance(meta, dict)
        else None
    )
    visible_ids = {group.id for group in visible}
    selected_id = (
        selected
        if isinstance(selected, int) and selected in visible_ids
        else None
    )
    return BoardGroupListOut(groups=groups, selected_id=selected_id)
