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

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app import teams_service
from app.api.dependencies import control_token, get_session, resolve_board_skey
from app.api.pagination import PAGINATED_RESPONSES, Page, PageDep, with_total
from app.api.schemas import is_acceptable_catalog_icon
from app.api.session_manager import GameSession
from app.api.session_persistence import load_session_meta
from app.auth.dependencies import current_user, require_admin, require_user
from app.constants import LIST_MAX_LIMIT
from app.db.engine import get_db
from app.db.models.team import Team, TeamGroup
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


# ---- schemas ---------------------------------------------------------------


class TeamOut(BaseModel):
    id: int
    name: str
    icon: str | None = None
    color: str | None = None
    text_color: str | None = None
    is_global: bool

    @classmethod
    def of(cls, t: Team) -> TeamOut:
        return cls(
            id=t.id, name=t.name, icon=t.icon_url, color=t.color,
            text_color=t.text_color, is_global=t.is_global,
        )


def _validate_catalog_icon(value: str | None) -> str | None:
    """Shared ``icon`` gate for every team write model.

    Permissive on purpose — legacy scheme-less values must keep
    round-tripping through PATCH — but positively dangerous strings
    (``javascript:`` and friends) are rejected at the door. See
    :func:`app.api.schemas.is_acceptable_catalog_icon`.
    """
    if value is not None and not is_acceptable_catalog_icon(value):
        raise ValueError("Icon URL scheme is not allowed.")
    return value


class CustomTeamRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    icon: str | None = Field(default=None, max_length=2048)
    color: str | None = Field(default=None, max_length=32)
    text_color: str | None = Field(default=None, max_length=32)

    _icon_ok = field_validator("icon")(_validate_catalog_icon)


class CustomTeamUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    icon: str | None = Field(default=None, max_length=2048)
    color: str | None = Field(default=None, max_length=32)
    text_color: str | None = Field(default=None, max_length=32)

    _icon_ok = field_validator("icon")(_validate_catalog_icon)


class TeamGroupOut(BaseModel):
    id: int
    name: str
    is_active: bool
    teams: list[TeamOut]


class AdminTeamRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    icon: str | None = Field(default=None, max_length=2048)
    color: str | None = Field(default=None, max_length=32)
    text_color: str | None = Field(default=None, max_length=32)

    _icon_ok = field_validator("icon")(_validate_catalog_icon)


class AdminTeamUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    icon: str | None = Field(default=None, max_length=2048)
    color: str | None = Field(default=None, max_length=32)
    text_color: str | None = Field(default=None, max_length=32)

    _icon_ok = field_validator("icon")(_validate_catalog_icon)


class ImportTeamsRequest(BaseModel):
    teams: dict[str, dict[str, Any]]
    replace: bool = False


class CreateGroupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class GroupMemberRequest(BaseModel):
    team_id: int


class SetActiveRequest(BaseModel):
    is_active: bool


# Groups-as-primary-unit schemas. ``id`` is ``None`` for the synthetic "All"
# group; ``kind`` is ``'all'`` | ``'shared'`` | ``'private'``.
class GroupDetailOut(BaseModel):
    id: int | None
    name: str
    kind: str
    is_private: bool
    teams: list[TeamOut]
    # Team ids the caller may remove from this group (their own additions). For
    # the "All" group and a shared group's admin-intrinsic members this is empty.
    removable_ids: list[int] = Field(default_factory=list)


class BoardGroupOut(BaseModel):
    id: int | None
    name: str
    kind: str
    count: int


class BoardGroupListOut(BaseModel):
    groups: list[BoardGroupOut]
    selected_id: int | None


class CreateMyGroupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class RenameMyGroupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class GroupTeamsRequest(BaseModel):
    team_ids: list[int] = Field(default_factory=list)


class SelectGroupRequest(BaseModel):
    group_id: int | None = None


_ALL_GROUP_NAME = "All teams"


def _all_group_detail(db: Session, user_id: int) -> GroupDetailOut:
    # The only nested roster that grows with the whole catalog rather than with
    # a curated membership, so it carries the hard ceiling — this endpoint pages
    # *groups*, so its X-Total-Count cannot describe a nested team list. A
    # caller that needs the complete roster pages it from
    # ``GET /teams/catalog?scope=all``, which covers the same global-∪-custom
    # set and reports its own total.
    teams = teams_service.all_group_teams(db, user_id, limit=LIST_MAX_LIMIT)
    return GroupDetailOut(
        id=None, name=_ALL_GROUP_NAME, kind="all", is_private=False,
        teams=[TeamOut.of(t) for t in teams],
    )


def _group_rows_out(db: Session, groups: list[TeamGroup]) -> list[TeamGroupOut]:
    """The admin shared-group listing with its curated members — one membership
    query for the whole page instead of one per group."""
    members = teams_service.group_member_teams_bulk(db, [g.id for g in groups])
    return [
        TeamGroupOut(
            id=g.id, name=g.name, is_active=g.is_active,
            teams=[TeamOut.of(t) for t in members[g.id]],
        )
        for g in groups
    ]


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
            db, user.id, body.name,
            icon=body.icon, color=body.color, text_color=body.text_color,
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
            db, user.id, team_id,
            name=body.name, icon=body.icon, color=body.color, text_color=body.text_color,
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
            db, body.name, icon=body.icon, color=body.color, text_color=body.text_color,
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
            db, team_id, name=body.name, icon=body.icon,
            color=body.color, text_color=body.text_color,
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
    _admin: User = Depends(require_admin), db: Session = Depends(get_db),
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
    return _group_rows_out(
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
    body: SetActiveRequest,
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


def _parse_group_key(group_key: str) -> int | None:
    """``"all"`` -> None (the virtual All group); else an int group id."""
    if group_key == "all":
        return None
    try:
        return int(group_key)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid group key.") from exc


@router.get("/board/team-groups", response_model=BoardGroupListOut)
def board_team_groups(
    skey: str = Depends(board_owner_skey), db: Session = Depends(get_db),
):
    owner_id, _oid = split_skey(skey)
    # Counts only — this runs on every board load, so it must never materialise
    # a ``Team`` row just to call ``len()`` on the list. Two aggregate queries
    # cover the whole picker no matter how many groups the owner has.
    visible = teams_service.list_user_visible_groups(db, owner_id)
    counts = teams_service.group_effective_counts(db, owner_id, visible)
    groups = [
        BoardGroupOut(
            id=None, name=_ALL_GROUP_NAME, kind="all",
            count=teams_service.all_group_team_count(db, owner_id),
        )
    ]
    groups.extend(
        BoardGroupOut(
            id=group.id, name=group.name, kind=teams_service.group_kind(group),
            count=counts.get(group.id, 0),
        )
        for group in visible
    )
    # Remembered selection (best-effort from persisted meta); drop it if the
    # group is no longer visible (deleted / unpublished) — resolved against the
    # listing we just built rather than with another DB round-trip.
    meta = load_session_meta(skey)
    selected = meta.get("selected_team_group_id") if isinstance(meta, dict) else None
    visible_ids = {group.id for group in visible}
    selected_id = selected if isinstance(selected, int) and selected in visible_ids else None
    return BoardGroupListOut(groups=groups, selected_id=selected_id)


@router.get("/board/team-groups/{group_key}/teams")
def board_group_teams(
    group_key: str,
    skey: str = Depends(board_owner_skey),
    db: Session = Depends(get_db),
):
    """The APP_TEAMS map for one group, consumed by the board team selectors."""
    owner_id, _oid = split_skey(skey)
    group_id = _parse_group_key(group_key)
    try:
        return teams_service.group_effective_teams_map(db, owner_id, group_id)
    except teams_service.TeamError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/board/selected-group")
def board_select_group(
    body: SelectGroupRequest,
    session: GameSession = Depends(get_session),
    db: Session = Depends(get_db),
):
    owner_id, _oid = split_skey(session.skey)
    if body.group_id is not None and teams_service.get_visible_group(
        db, owner_id, body.group_id,
    ) is None:
        raise HTTPException(status_code=404, detail="Group not found.")
    from app.api.game_service import GameService
    GameService.set_selected_team_group(session, body.group_id)
    return {"ok": True, "selected_id": session.selected_team_group_id}


# ---- account: my groups (require_user) -------------------------------------


def _details_for(
    db: Session, user_id: int, groups: list[TeamGroup],
) -> list[GroupDetailOut]:
    """Render several groups at a fixed query cost: one for the user's own
    additions (which double as ``removable_ids``) and one for the shared
    groups' admin-intrinsic members."""
    additions = teams_service.user_group_teams_bulk(
        db, user_id, [g.id for g in groups],
    )
    effective = teams_service.group_effective_teams_bulk(
        db, user_id, groups, user_additions=additions,
    )
    return [
        GroupDetailOut(
            id=group.id, name=group.name,
            kind=teams_service.group_kind(group),
            is_private=group.owner_user_id is not None,
            teams=[TeamOut.of(t) for t in effective[group.id]],
            removable_ids=sorted(t.id for t in additions[group.id]),
        )
        for group in groups
    ]


def _group_detail(db: Session, user_id: int, group: TeamGroup) -> GroupDetailOut:
    return _details_for(db, user_id, [group])[0]


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
    details = _details_for(db, user.id, groups)
    return [_all_group_detail(db, user.id), *details] if include_all else details


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
    return _group_detail(db, user.id, group)


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
    return _group_detail(db, user.id, group)


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
