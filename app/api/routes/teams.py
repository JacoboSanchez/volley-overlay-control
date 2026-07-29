"""Teams + groups API.

Groups are the primary unit of team selection:

- ``GET  /api/v1/my/groups``             the caller's groups ("All" + shared + private), with teams
- ``POST /api/v1/my/groups``             create a private group
- ``POST /api/v1/my/groups/{id}/teams``  add team(s) to a group (private member or shared-group extension)
- ``GET  /api/v1/board/team-groups``     the board picker options (board-control auth → owner's groups)
- ``GET  /api/v1/board/team-groups/{key}/teams``  a group's teams in APP_TEAMS shape for the board
- ``PUT  /api/v1/board/selected-group``  remember the board's selected group (per overlay)
- ``/api/v1/admin/teams*`` + ``/admin/team-groups*``  admin catalog + shared-group authoring

Personal teams are owned rather than listed: ``POST``/``PATCH``
``/api/v1/teams/mine/custom`` author them and ``DELETE /api/v1/teams/mine/{id}``
deletes one outright. Ownership alone puts a team in the virtual "All" group.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app import teams_service
from app.api import team_groups_service
from app.api.dependencies import control_token, get_session, resolve_board_skey
from app.api.pagination import PAGINATED_RESPONSES, Page, PageDep, with_total
from app.api.schemas import (
    AdminTeamRequest,
    AdminTeamUpdateRequest,
    BoardGroupListOut,
    CreateGroupRequest,
    CreateMyGroupRequest,
    CustomTeamRequest,
    CustomTeamUpdateRequest,
    GroupDetailOut,
    GroupMemberRequest,
    GroupTeamsRequest,
    ImportTeamsRequest,
    RenameMyGroupRequest,
    SelectGroupRequest,
    TeamGroupOut,
    TeamGroupSetActiveRequest,
    TeamOut,
)
from app.api.session_manager import GameSession
from app.auth.dependencies import current_user, require_admin, require_user
from app.db.engine import get_db
from app.db.models.team import Team
from app.db.models.user import User
from app.overlay_key import split_skey

router = APIRouter()


def board_owner_skey(
    oid: str | None = Query(None, description="Overlay ID"),
    control: str | None = Query(None, description="Alias of `oid`"),
    token: str | None = Depends(control_token),
    u: str | None = Query(None, description="Username for a public ?u=&oid= board URL"),
    user: User | None = Depends(current_user),
    db: Session = Depends(get_db),
) -> str:
    """Resolve the board's storage key from whichever board credential is present
    (control token / public bookmark / owner cookie). Used by the board team
    picker so operators (no cookie) reach the OWNER's groups, not their own."""
    return resolve_board_skey(db, token=token, public_user=u, user=user, oid=(oid or control))


# ---- user-facing -----------------------------------------------------------


@router.get(
    "/teams/catalog", response_model=list[TeamOut], responses=PAGINATED_RESPONSES,
)
def catalog(
    response: Response,
    scope: Literal["global", "all"] = Query(
        "global",
        description=(
            "`global` (default) is the admin catalog. `all` is the caller's "
            "whole universe — every global team plus their own custom teams — "
            "i.e. the same set as the synthetic \"All teams\" group."
        ),
    ),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
    page: Page = PageDep,
):
    """The team catalog, paged.

    ``scope=all`` exists so the "All teams" roster has a pageable home of its
    own: ``GET /my/groups`` embeds that roster but pages *groups*, so its
    ``X-Total-Count`` cannot describe a nested team list. Without this a large
    universe would be truncated there with no way to fetch the remainder —
    ``scope=global`` alone would miss the caller's custom teams.
    """
    if scope == "all":
        with_total(response, teams_service.all_group_team_count(db, user.id))
        rows = teams_service.all_group_teams(
            db, user.id, limit=page.limit, offset=page.offset,
        )
    else:
        with_total(response, teams_service.count_global(db))
        rows = teams_service.list_global(db, limit=page.limit, offset=page.offset)
    return [TeamOut.of(t) for t in rows]


@router.post("/teams/mine/custom", response_model=TeamOut, status_code=201)
def create_my_custom_team(
    body: CustomTeamRequest,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Create a personal team and add it to the caller's list."""
    try:
        team = teams_service.create_user_team(
            db,
            user.id,
            body.name,
            icon=body.icon,
            color=body.color,
            text_color=body.text_color,
        )
    except teams_service.TeamError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return TeamOut.of(team)


@router.patch("/teams/mine/custom/{team_id}", response_model=TeamOut)
def update_my_custom_team(
    team_id: int,
    body: CustomTeamUpdateRequest,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Edit one of the caller's own custom teams."""
    try:
        team = teams_service.update_user_team(
            db,
            user.id,
            team_id,
            name=body.name,
            icon=body.icon,
            color=body.color,
            text_color=body.text_color,
        )
    except teams_service.TeamError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
    return TeamOut.of(team)


@router.delete("/teams/mine/{team_id}")
def delete_my_custom_team(
    team_id: int,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Delete one of the caller's own custom teams, dropping it from every group.

    Global teams belong to the admin catalog — remove those from a single group
    via ``DELETE /my/groups/{group_id}/teams/{team_id}`` instead.
    """
    if not teams_service.delete_user_team(db, user.id, team_id):
        raise HTTPException(status_code=404, detail="Not one of your custom teams.")
    db.commit()
    return {"ok": True}


# ---- admin authoring -------------------------------------------------------


@router.post("/admin/teams", response_model=TeamOut, status_code=201)
def admin_create_team(
    body: AdminTeamRequest,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        team = teams_service.upsert_global(
            db,
            body.name,
            icon=body.icon,
            color=body.color,
            text_color=body.text_color,
        )
    except teams_service.TeamError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return TeamOut.of(team)


@router.patch("/admin/teams/{team_id}", response_model=TeamOut)
def admin_update_team(
    team_id: int,
    body: AdminTeamUpdateRequest,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        team = teams_service.update_global(
            db,
            team_id,
            name=body.name,
            icon=body.icon,
            color=body.color,
            text_color=body.text_color,
        )
    except teams_service.TeamError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
    return TeamOut.of(team)


@router.delete("/admin/teams/{team_id}")
def admin_delete_team(
    team_id: int,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if not teams_service.delete_global(db, team_id):
        raise HTTPException(status_code=404, detail="Team not found.")
    db.commit()
    return {"ok": True}


@router.get("/admin/teams/export")
def admin_export_teams(
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Export the global catalog as an APP_TEAMS JSON map."""
    return teams_service.export_app_teams(db)


@router.post("/admin/teams/import")
def admin_import_teams(
    body: ImportTeamsRequest,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Import an APP_TEAMS JSON map into the global catalog (upsert by name)."""
    try:
        count = teams_service.import_app_teams(db, body.teams, replace=body.replace)
    except teams_service.TeamError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return {"imported": count}


@router.get(
    "/admin/team-groups", response_model=list[TeamGroupOut],
    responses=PAGINATED_RESPONSES,
)
def admin_list_groups(
    response: Response,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    page: Page = PageDep,
):
    """Every group (active and inactive) with its members — drives the admin
    group manager."""
    with_total(response, teams_service.count_all_groups(db))
    return team_groups_service.admin_group_rows(
        db, teams_service.list_all_groups(db, limit=page.limit, offset=page.offset),
    )


@router.post("/admin/team-groups", response_model=TeamGroupOut, status_code=201)
def admin_create_group(
    body: CreateGroupRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        group = teams_service.create_group(db, body.name, created_by_user_id=admin.id)
    except teams_service.TeamError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return TeamGroupOut(id=group.id, name=group.name, is_active=group.is_active, teams=[])


@router.post("/admin/team-groups/{group_id}/members")
def admin_add_group_member(
    group_id: int,
    body: GroupMemberRequest,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if teams_service.get_shared_group(db, group_id) is None:
        raise HTTPException(status_code=404, detail="Group not found.")
    team = db.get(Team, body.team_id)
    # Groups are a curated catalog of GLOBAL teams; a user-owned custom team must
    # never be linked (it would leak that user's private team into everyone's
    # roster via copy-to-mine). Mirror the global-only guard on update/delete.
    if team is None or not team.is_global:
        raise HTTPException(status_code=404, detail="Team not found.")
    teams_service.add_group_member(db, group_id, body.team_id)
    db.commit()
    return {"ok": True}


@router.delete("/admin/team-groups/{group_id}/members/{team_id}")
def admin_remove_group_member(
    group_id: int,
    team_id: int,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if teams_service.get_shared_group(db, group_id) is None:
        raise HTTPException(status_code=404, detail="Group not found.")
    removed = teams_service.remove_group_member(db, group_id, team_id)
    db.commit()
    return {"ok": True, "removed": removed}


@router.patch("/admin/team-groups/{group_id}")
def admin_set_group_active(
    group_id: int,
    body: TeamGroupSetActiveRequest,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        group = teams_service.set_group_active(db, group_id, body.is_active)
    except teams_service.TeamError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
    return {"id": group.id, "is_active": group.is_active}


@router.delete("/admin/team-groups/{group_id}")
def admin_delete_group(
    group_id: int,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if not teams_service.delete_group(db, group_id):
        raise HTTPException(status_code=404, detail="Group not found.")
    db.commit()
    return {"ok": True}


# ---- board team picker (board-control auth) --------------------------------
# These resolve the OWNER's universe from the board credential (control token /
# public bookmark / owner cookie), so an operator running the match sees the
# owner's groups — fixing the old ``GET /teams`` which only worked for the owner
# cookie and left operators with an empty picker.


@router.get("/board/team-groups", response_model=BoardGroupListOut)
def board_team_groups(
    skey: str = Depends(board_owner_skey),
    db: Session = Depends(get_db),
):
    owner_id, _oid = split_skey(skey)
    return team_groups_service.board_group_list(db, owner_id, skey)


@router.get("/board/team-groups/{group_key}/teams")
def board_group_teams(
    group_key: str,
    skey: str = Depends(board_owner_skey),
    db: Session = Depends(get_db),
):
    """The APP_TEAMS map for one group, consumed by the board team selectors."""
    owner_id, _oid = split_skey(skey)
    try:
        group_id = team_groups_service.parse_group_key(group_key)
        return teams_service.group_effective_teams_map(db, owner_id, group_id)
    except teams_service.TeamError as exc:
        status_code = 422 if str(exc) == "Invalid group key." else 404
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.put("/board/selected-group")
def board_select_group(
    body: SelectGroupRequest,
    session: GameSession = Depends(get_session),
    db: Session = Depends(get_db),
):
    owner_id, _oid = split_skey(session.skey)
    if (
        body.group_id is not None
        and teams_service.get_visible_group(
            db,
            owner_id,
            body.group_id,
        )
        is None
    ):
        raise HTTPException(status_code=404, detail="Group not found.")
    from app.api.game_service import GameService

    GameService.set_selected_team_group(session, body.group_id)
    return {"ok": True, "selected_id": session.selected_team_group_id}


# ---- account: my groups (require_user) -------------------------------------


@router.get(
    "/my/groups", response_model=list[GroupDetailOut], responses=PAGINATED_RESPONSES,
)
def my_visible_groups(
    response: Response,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
    page: Page = PageDep,
):
    """The caller's selectable groups: the synthetic "All" first, then shared
    published groups and the user's own private groups, each with their teams.

    ``limit``/``offset`` page the *groups*; the synthetic "All" entry is the
    first row of that sequence, so ``X-Total-Count`` is one more than the
    number of real groups.
    """
    with_total(response, teams_service.count_user_visible_groups(db, user.id) + 1)
    # "All" occupies index 0 of the paged sequence, so a non-zero offset both
    # drops it and shifts the real-group window back by one.
    include_all = page.offset == 0
    groups = teams_service.list_user_visible_groups(
        db, user.id,
        limit=page.limit - 1 if include_all else page.limit,
        offset=0 if include_all else page.offset - 1,
    )
    details = team_groups_service.group_details(db, user.id, groups)
    return (
        [team_groups_service.all_group_detail(db, user.id), *details]
        if include_all
        else details
    )


@router.post("/my/groups", response_model=GroupDetailOut, status_code=201)
def create_my_group(
    body: CreateMyGroupRequest,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        group = teams_service.create_private_group(db, user.id, body.name)
    except teams_service.TeamError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return team_groups_service.group_detail(db, user.id, group)


@router.patch("/my/groups/{group_id}", response_model=GroupDetailOut)
def rename_my_group(
    group_id: int,
    body: RenameMyGroupRequest,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        group = teams_service.rename_private_group(db, user.id, group_id, body.name)
    except teams_service.TeamError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
    return team_groups_service.group_detail(db, user.id, group)


@router.delete("/my/groups/{group_id}")
def delete_my_group(
    group_id: int,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    if not teams_service.delete_private_group(db, user.id, group_id):
        raise HTTPException(status_code=404, detail="Group not found.")
    db.commit()
    return {"ok": True}


@router.post("/my/groups/{group_id}/teams")
def add_teams_to_my_group(
    group_id: int,
    body: GroupTeamsRequest,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        added = teams_service.add_user_group_teams(db, user.id, group_id, body.team_ids)
    except teams_service.TeamError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
    return {"added": added}


@router.delete("/my/groups/{group_id}/teams/{team_id}")
def remove_team_from_my_group(
    group_id: int,
    team_id: int,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    if teams_service.get_visible_group(db, user.id, group_id) is None:
        raise HTTPException(status_code=404, detail="Group not found.")
    removed = teams_service.remove_user_group_team(db, user.id, group_id, team_id)
    db.commit()
    return {"ok": True, "removed": removed}
