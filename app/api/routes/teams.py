"""Teams API: per-user lists, the global catalog, and admin authoring.

- ``GET  /api/v1/teams``                 the caller's team list (APP_TEAMS shape)
- ``GET  /api/v1/teams/catalog``         the global catalog with ids
- ``POST /api/v1/teams/mine``            add catalog teams to my list
- ``DELETE /api/v1/teams/mine/{id}``     remove one from my list
- ``GET  /api/v1/team-groups``           active groups (admin-published)
- ``POST /api/v1/team-groups/{id}/copy-to-mine``  copy a group into my list
- ``/api/v1/admin/teams*`` + ``/admin/team-groups*``  admin authoring + JSON import/export
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import teams_service
from app.auth.dependencies import require_admin, require_user
from app.db.engine import get_db
from app.db.models.team import Team, TeamGroup
from app.db.models.user import User

router = APIRouter()


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


class AddTeamsRequest(BaseModel):
    team_ids: list[int] = Field(default_factory=list)


class RemoveTeamsRequest(BaseModel):
    team_ids: list[int] = Field(default_factory=list)


class CustomTeamRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    icon: str | None = Field(default=None, max_length=2048)
    color: str | None = Field(default=None, max_length=32)
    text_color: str | None = Field(default=None, max_length=32)


class CustomTeamUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    icon: str | None = Field(default=None, max_length=2048)
    color: str | None = Field(default=None, max_length=32)
    text_color: str | None = Field(default=None, max_length=32)


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


class AdminTeamUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    icon: str | None = Field(default=None, max_length=2048)
    color: str | None = Field(default=None, max_length=32)
    text_color: str | None = Field(default=None, max_length=32)


class ImportTeamsRequest(BaseModel):
    teams: dict[str, dict[str, Any]]
    replace: bool = False


class CreateGroupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class GroupMemberRequest(BaseModel):
    team_id: int


class SetActiveRequest(BaseModel):
    is_active: bool


# ---- user-facing -----------------------------------------------------------


@router.get("/teams")
async def my_teams(user: User = Depends(require_user), db: Session = Depends(get_db)):
    """The caller's team list, in the APP_TEAMS map shape."""
    return teams_service.user_teams(db, user.id)


@router.get("/teams/mine", response_model=list[TeamOut])
async def my_team_rows(user: User = Depends(require_user), db: Session = Depends(get_db)):
    """The caller's team list as rows with ids (global + own custom teams)."""
    return [TeamOut.of(t) for t in teams_service.list_user_team_rows(db, user.id)]


@router.get("/teams/catalog", response_model=list[TeamOut])
async def catalog(user: User = Depends(require_user), db: Session = Depends(get_db)):
    return [TeamOut.of(t) for t in teams_service.list_global(db)]


@router.post("/teams/mine")
async def add_to_my_teams(
    body: AddTeamsRequest,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        added = teams_service.add_teams_to_user(db, user.id, body.team_ids)
    except teams_service.TeamError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return {"added": added}


@router.post("/teams/mine/custom", response_model=TeamOut, status_code=201)
async def create_my_custom_team(
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
async def update_my_custom_team(
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


@router.post("/teams/mine/remove")
async def remove_my_teams(
    body: RemoveTeamsRequest,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Batch-remove teams from the caller's list (unlinks globals; deletes own customs)."""
    removed = teams_service.remove_teams_from_user(db, user.id, body.team_ids)
    db.commit()
    return {"removed": removed}


@router.delete("/teams/mine/{team_id}")
async def remove_from_my_teams(
    team_id: int,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    if not teams_service.remove_team_from_user(db, user.id, team_id):
        raise HTTPException(status_code=404, detail="Not in your team list.")
    db.commit()
    return {"ok": True}


@router.get("/team-groups", response_model=list[TeamGroupOut])
async def list_groups(user: User = Depends(require_user), db: Session = Depends(get_db)):
    out = []
    for g in teams_service.list_active_groups(db):
        teams = [TeamOut.of(t) for t in teams_service.group_member_teams(db, g.id)]
        out.append(TeamGroupOut(id=g.id, name=g.name, is_active=g.is_active, teams=teams))
    return out


@router.post("/team-groups/{group_id}/copy-to-mine")
async def copy_group(
    group_id: int,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    try:
        added = teams_service.copy_group_to_user(db, user.id, group_id)
    except teams_service.TeamError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
    return {"added": added}


# ---- admin authoring -------------------------------------------------------


@router.post("/admin/teams", response_model=TeamOut, status_code=201)
async def admin_create_team(
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
async def admin_update_team(
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
async def admin_delete_team(
    team_id: int,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if not teams_service.delete_global(db, team_id):
        raise HTTPException(status_code=404, detail="Team not found.")
    db.commit()
    return {"ok": True}


@router.get("/admin/teams/export")
async def admin_export_teams(
    _admin: User = Depends(require_admin), db: Session = Depends(get_db),
):
    """Export the global catalog as an APP_TEAMS JSON map."""
    return teams_service.export_app_teams(db)


@router.post("/admin/teams/import")
async def admin_import_teams(
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


@router.get("/admin/team-groups", response_model=list[TeamGroupOut])
async def admin_list_groups(
    _admin: User = Depends(require_admin), db: Session = Depends(get_db),
):
    """Every group (active and inactive) with its members — drives the admin
    group manager. Users only ever see active groups via ``GET /team-groups``."""
    out = []
    for g in teams_service.list_all_groups(db):
        teams = [TeamOut.of(t) for t in teams_service.group_member_teams(db, g.id)]
        out.append(TeamGroupOut(id=g.id, name=g.name, is_active=g.is_active, teams=teams))
    return out


@router.post("/admin/team-groups", response_model=TeamGroupOut, status_code=201)
async def admin_create_group(
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
async def admin_add_group_member(
    group_id: int,
    body: GroupMemberRequest,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if db.get(TeamGroup, group_id) is None:
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
async def admin_remove_group_member(
    group_id: int,
    team_id: int,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if db.get(TeamGroup, group_id) is None:
        raise HTTPException(status_code=404, detail="Group not found.")
    removed = teams_service.remove_group_member(db, group_id, team_id)
    db.commit()
    return {"ok": True, "removed": removed}


@router.patch("/admin/team-groups/{group_id}")
async def admin_set_group_active(
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
async def admin_delete_group(
    group_id: int,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if not teams_service.delete_group(db, group_id):
        raise HTTPException(status_code=404, detail="Group not found.")
    db.commit()
    return {"ok": True}
