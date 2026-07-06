"""Hosted icon library API.

Personal scope (``require_user``):

- ``GET    /api/v1/icons``                      globals + mine + quota (feeds the picker)
- ``POST   /api/v1/icons/mine``                 multipart upload (file + name)
- ``PATCH  /api/v1/icons/mine/{id}``            rename
- ``GET    /api/v1/icons/mine/{id}/usage``      how many teams reference it
- ``DELETE /api/v1/icons/mine/{id}``            delete + clear referencing teams
- ``POST   /api/v1/icons/mine/import-from-teams``   convert own teams' external logos

Admin scope (``require_admin``) mirrors the same shapes for global icons
under ``/api/v1/admin/icons*`` (imports convert *global* teams).

The image files themselves are served by the unauthenticated ``/media``
static mount — overlay pages in OBS carry no cookies.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app import icons_service
from app.auth.dependencies import require_admin, require_user
from app.constants import (
    ICONS_IMPORT_MAX_BATCH,
    ICONS_MAX_PER_USER,
    ICONS_MAX_UPLOAD_BYTES,
)
from app.db.engine import get_db
from app.db.models.icon import Icon
from app.db.models.team import Team
from app.db.models.user import User

router = APIRouter()


# ---- schemas ----------------------------------------------------------------


class IconOut(BaseModel):
    id: int
    name: str
    url: str
    is_global: bool
    width: int
    height: int
    size_bytes: int

    @classmethod
    def of(cls, icon: Icon) -> IconOut:
        return cls(
            id=icon.id,
            name=icon.name,
            url=icons_service.icon_public_url(icon.filename),
            is_global=icon.is_global,
            width=icon.width,
            height=icon.height,
            size_bytes=icon.size_bytes,
        )


class IconQuotaOut(BaseModel):
    used: int
    limit: int


class IconLibraryOut(BaseModel):
    globals: list[IconOut]
    mine: list[IconOut]
    quota: IconQuotaOut


class IconRenameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class IconUsageOut(BaseModel):
    teams: int


class IconDeleteOut(BaseModel):
    ok: bool
    teams_cleared: int


class IconImportRequest(BaseModel):
    team_ids: list[int] = Field(default_factory=list)


class IconImportResult(BaseModel):
    team_id: int
    team_name: str
    status: str
    icon_id: int | None = None
    icon_url: str | None = None
    error: str | None = None


class IconImportOut(BaseModel):
    results: list[IconImportResult]


# ---- helpers -----------------------------------------------------------------


def _reject_oversized_body(request: Request) -> None:
    """Fast-fail uploads whose declared size already busts the cap.

    Browsers always send Content-Length for FormData bodies, so this
    rejects a 50 MB file before any bytes are parsed. A client that
    lies (or chunks) is still bounded by the streamed read below.
    """
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > ICONS_MAX_UPLOAD_BYTES + 8192:
        raise HTTPException(status_code=413, detail="Image is too large.")


async def _read_upload_capped(file: UploadFile) -> bytes:
    chunks: list[bytes] = []
    received = 0
    while chunk := await file.read(64 * 1024):
        received += len(chunk)
        if received > ICONS_MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Image is too large.")
        chunks.append(chunk)
    return b"".join(chunks)


def _create_icon_sync(
    db: Session, *, name: str, raw: bytes, user_id: int | None
) -> IconOut:
    """Blocking tail of an upload (Pillow processing + commit) — must run
    in the threadpool, never on the event loop."""
    try:
        icon = icons_service.create_icon(db, name=name, raw=raw, user_id=user_id)
    except icons_service.IconError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return IconOut.of(icon)


async def _create_icon_endpoint(
    db: Session, *, name: str, file: UploadFile, user_id: int | None
) -> IconOut:
    raw = await _read_upload_capped(file)
    return await run_in_threadpool(
        _create_icon_sync, db, name=name, raw=raw, user_id=user_id,
    )


def _get_scoped_or_404(db: Session, icon_id: int, *, user_id: int | None) -> Icon:
    icon = icons_service.get_scoped(db, icon_id, user_id=user_id)
    if icon is None:
        raise HTTPException(status_code=404, detail="Icon not found.")
    return icon


def _rename_endpoint(
    db: Session, icon_id: int, name: str, *, user_id: int | None
) -> IconOut:
    icon = _get_scoped_or_404(db, icon_id, user_id=user_id)
    try:
        icons_service.rename_icon(db, icon, name)
    except icons_service.IconError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return IconOut.of(icon)


def _delete_endpoint(db: Session, icon_id: int, *, user_id: int | None) -> IconDeleteOut:
    icon = _get_scoped_or_404(db, icon_id, user_id=user_id)
    cleared, filename = icons_service.delete_icon(db, icon)
    db.commit()
    # Capture → commit → cleanup, like delete_user: the file goes only
    # once the row deletion is durable.
    icons_service.unlink_files([filename])
    return IconDeleteOut(ok=True, teams_cleared=cleared)


def _import_endpoint(
    db: Session, team_ids: list[int], *, scope_user_id: int | None
) -> IconImportOut:
    """Resolve *team_ids* inside the caller's scope and convert them.

    The scope filter is server-enforced: the personal variant only ever
    touches the caller's own teams, the admin variant only global ones —
    ids outside the scope surface as per-team "not found" errors rather
    than silently rewriting someone else's rows.
    """
    # Dedupe before the batch cap so repeated ids neither inflate the
    # count nor produce duplicate result rows for the same team.
    team_ids = list(dict.fromkeys(team_ids))
    if len(team_ids) > ICONS_IMPORT_MAX_BATCH:
        raise HTTPException(
            status_code=400,
            detail=f"Too many teams in one import (max {ICONS_IMPORT_MAX_BATCH}).",
        )
    query = db.query(Team).filter(Team.id.in_(team_ids or []))
    if scope_user_id is None:
        query = query.filter(Team.is_global.is_(True))
    else:
        query = query.filter(Team.owner_user_id == scope_user_id)
    by_id = {t.id: t for t in query.all()}
    ordered = [by_id[tid] for tid in team_ids if tid in by_id]
    results = icons_service.import_icons_from_teams(
        db, ordered, user_id=scope_user_id,
    )
    known = {r["team_id"] for r in results}
    for tid in team_ids:
        if tid not in known:
            results.append(
                {
                    "team_id": tid,
                    "team_name": "",
                    "status": "error",
                    "error": "team not found in this scope",
                }
            )
    return IconImportOut(results=[IconImportResult(**r) for r in results])


# ---- personal scope ----------------------------------------------------------


@router.get("/icons", response_model=IconLibraryOut)
def list_icons(
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    return IconLibraryOut(
        globals=[IconOut.of(i) for i in icons_service.list_global(db)],
        mine=[IconOut.of(i) for i in icons_service.list_mine(db, user.id)],
        quota=IconQuotaOut(
            used=icons_service.user_icon_count(db, user.id),
            limit=ICONS_MAX_PER_USER,
        ),
    )


@router.post(
    "/icons/mine",
    response_model=IconOut,
    status_code=201,
    dependencies=[Depends(_reject_oversized_body)],
)
async def upload_my_icon(
    name: str = Form(min_length=1, max_length=120),
    file: UploadFile = File(...),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    return await _create_icon_endpoint(db, name=name, file=file, user_id=user.id)


@router.patch("/icons/mine/{icon_id}", response_model=IconOut)
def rename_my_icon(
    icon_id: int,
    body: IconRenameRequest,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    return _rename_endpoint(db, icon_id, body.name, user_id=user.id)


@router.get("/icons/mine/{icon_id}/usage", response_model=IconUsageOut)
def my_icon_usage(
    icon_id: int,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    icon = _get_scoped_or_404(db, icon_id, user_id=user.id)
    return IconUsageOut(teams=icons_service.usage_count(db, icon))


@router.delete("/icons/mine/{icon_id}", response_model=IconDeleteOut)
def delete_my_icon(
    icon_id: int,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    return _delete_endpoint(db, icon_id, user_id=user.id)


@router.post("/icons/mine/import-from-teams", response_model=IconImportOut)
def import_icons_from_my_teams(
    body: IconImportRequest,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    return _import_endpoint(db, body.team_ids, scope_user_id=user.id)


# ---- admin scope (global icons) ----------------------------------------------


@router.post(
    "/admin/icons",
    response_model=IconOut,
    status_code=201,
    dependencies=[Depends(_reject_oversized_body)],
)
async def admin_upload_icon(
    name: str = Form(min_length=1, max_length=120),
    file: UploadFile = File(...),
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return await _create_icon_endpoint(db, name=name, file=file, user_id=None)


@router.patch("/admin/icons/{icon_id}", response_model=IconOut)
def admin_rename_icon(
    icon_id: int,
    body: IconRenameRequest,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return _rename_endpoint(db, icon_id, body.name, user_id=None)


@router.get("/admin/icons/{icon_id}/usage", response_model=IconUsageOut)
def admin_icon_usage(
    icon_id: int,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    icon = _get_scoped_or_404(db, icon_id, user_id=None)
    return IconUsageOut(teams=icons_service.usage_count(db, icon))


@router.delete("/admin/icons/{icon_id}", response_model=IconDeleteOut)
def admin_delete_icon(
    icon_id: int,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return _delete_endpoint(db, icon_id, user_id=None)


@router.post("/admin/icons/import-from-teams", response_model=IconImportOut)
def admin_import_icons_from_teams(
    body: IconImportRequest,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return _import_endpoint(db, body.team_ids, scope_user_id=None)
