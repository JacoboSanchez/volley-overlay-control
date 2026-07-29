"""GET/PUT /customization — team names, colors, logos, theme overrides.

Plus an operator-facing preset CRUD that lives at
``/api/v1/customization/presets/*``: anyone with the API key can list,
save, or delete a named subset of the current customization model.
Apply is intentionally client-side (the React panel deep-merges a
preset's ``values`` into its in-memory edit model and persists with
the existing ``Save`` flow), so the picker UX stays consistent with
direct field edits and never races unsaved changes.

The list endpoint also surfaces env-driven themes from ``APP_THEMES``
as read-only ``source="system"`` records, so the React picker can show
both sources in a single list. System presets cannot be deleted.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Path, Response, status
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app import presets_service
from app.api.dependencies import get_session
from app.api.game_service import GameService
from app.api.pagination import PAGINATED_RESPONSES, Page, PageDep, with_total
from app.api.schemas import (
    ActionResponse,
    AdminPresetCreateRequest,
    CustomizationUpdateRequest,
    ImportThemesRequest,
    PresetCreateRequest,
    PresetListResponse,
    PresetSetActiveRequest,
    PresetSummary,
)
from app.api.session_manager import GameSession
from app.auth.dependencies import require_admin, require_user
from app.db.engine import get_db
from app.db.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/customization")
async def get_customization(session: GameSession = Depends(get_session)):
    return await run_in_threadpool(GameService.refresh_customization, session)


@router.put(
    "/customization",
    response_model=ActionResponse,
)
async def update_customization(
    data: CustomizationUpdateRequest,
    session: GameSession = Depends(get_session),
):
    async with session.lock:
        logger.debug("Customization updated (%d keys)", len(data.root))
        return GameService.update_customization(session, data.root)


# ---------------------------------------------------------------------------
# Operator-facing preset CRUD
# ---------------------------------------------------------------------------


@router.get(
    "/customization/presets",
    response_model=PresetListResponse,
    summary="List active global presets plus the caller's own.",
    responses=PAGINATED_RESPONSES,
)
def list_presets(
    response: Response,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
    page: Page = PageDep,
) -> PresetListResponse:
    with_total(response, presets_service.count_for_user(db, user.id))
    rows = presets_service.list_for_user(
        db, user.id, limit=page.limit, offset=page.offset,
    )
    return PresetListResponse(items=[PresetSummary.of(p) for p in rows])


@router.post(
    "/customization/presets",
    response_model=PresetSummary,
    summary="Save a subset of the current configuration as a personal preset.",
)
def create_preset(
    payload: PresetCreateRequest,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> PresetSummary:
    """Create a per-user preset (usable across all the caller's scoreboards)."""
    try:
        preset = presets_service.create_user_preset(
            db,
            user.id,
            payload.name,
            payload.values,
        )
    except presets_service.PresetError as exc:
        detail = str(exc)
        status_code = 409 if "already exists" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from None
    db.commit()
    return PresetSummary.of(preset)


@router.delete(
    "/customization/presets/{slug}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete one of the caller's own presets.",
)
def delete_preset(
    slug: str = Path(..., min_length=1, max_length=120),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> None:
    # Try the caller's own preset first: a user preset and a global preset may
    # legitimately share a slug, so the 403 global guard must not shadow the
    # user's own deletable row. delete_user_preset is scope-restricted to the
    # owner's user-scoped rows, so it can never touch a global.
    if presets_service.delete_user_preset(db, user.id, slug):
        db.commit()
        return
    if presets_service.get_global_preset(db, slug) is not None:
        raise HTTPException(
            status_code=403,
            detail="Global presets are managed by an administrator.",
        )
    raise HTTPException(status_code=404, detail=f"Preset '{slug}' not found.")


# ---- admin global-preset authoring ----------------------------------------


@router.get(
    "/admin/presets",
    response_model=PresetListResponse,
    summary="List all global presets (active and inactive) for management.",
    responses=PAGINATED_RESPONSES,
)
def admin_list_presets(
    response: Response,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    page: Page = PageDep,
) -> PresetListResponse:
    with_total(response, presets_service.count_global_presets(db))
    rows = presets_service.list_global_presets(
        db, limit=page.limit, offset=page.offset,
    )
    return PresetListResponse(items=[PresetSummary.of(p) for p in rows])


@router.post(
    "/admin/presets",
    response_model=PresetSummary,
    status_code=201,
    summary="Author a global preset.",
)
def admin_create_preset(
    payload: AdminPresetCreateRequest,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> PresetSummary:
    try:
        preset = presets_service.create_global_preset(
            db,
            payload.name,
            payload.values,
            is_active=payload.is_active,
        )
    except presets_service.PresetError as exc:
        detail = str(exc)
        status_code = 409 if "already exists" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from None
    db.commit()
    return PresetSummary.of(preset)


@router.patch("/admin/presets/{slug}", summary="Activate/deactivate a global preset.")
def admin_set_preset_active(
    body: PresetSetActiveRequest,
    slug: str = Path(..., min_length=1, max_length=120),
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        preset = presets_service.set_global_active(db, slug, body.is_active)
    except presets_service.PresetError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    db.commit()
    return {"slug": preset.slug, "is_active": preset.is_active}


@router.delete(
    "/admin/presets/{slug}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a global preset.",
)
def admin_delete_preset(
    slug: str = Path(..., min_length=1, max_length=120),
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    if not presets_service.delete_global_preset(db, slug):
        raise HTTPException(status_code=404, detail=f"Global preset '{slug}' not found.")
    db.commit()


@router.get("/admin/presets/export", summary="Export global presets as APP_THEMES JSON.")
def admin_export_presets(
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return presets_service.export_app_themes(db)


@router.post("/admin/presets/import", summary="Import an APP_THEMES JSON map.")
def admin_import_presets(
    body: ImportThemesRequest,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        count = presets_service.import_app_themes(db, body.themes, replace=body.replace)
    except presets_service.PresetError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    db.commit()
    return {"imported": count}
