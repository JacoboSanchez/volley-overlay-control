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
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app import presets_service
from app.api.dependencies import get_session, verify_api_key
from app.api.game_service import GameService
from app.api.schemas import ActionResponse
from app.api.session_manager import GameSession
from app.auth.dependencies import require_admin, require_user
from app.db.engine import get_db
from app.db.models.preset import Preset
from app.db.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/customization", dependencies=[Depends(verify_api_key)])
async def get_customization(session: GameSession = Depends(get_session)):
    return await run_in_threadpool(GameService.refresh_customization, session)


@router.put(
    "/customization",
    response_model=ActionResponse,
    dependencies=[Depends(verify_api_key)],
)
async def update_customization(data: dict,
                               session: GameSession = Depends(get_session)):
    async with session.lock:
        logger.debug("Customization updated (%d keys)", len(data))
        return GameService.update_customization(session, data)


# ---------------------------------------------------------------------------
# Operator-facing preset CRUD
# ---------------------------------------------------------------------------


class PresetSummary(BaseModel):
    slug: str
    name: str
    source: Literal["user", "global"] = Field(
        "user",
        description="``user`` for the caller's own presets; ``global`` for "
        "admin-authored, admin-activated presets shared with everyone. "
        "Only the owner may delete a ``user`` preset; globals are admin-only.",
    )
    is_active: bool = True
    categories: list[str] = Field(default_factory=list)
    values: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def of(cls, p: Preset) -> "PresetSummary":
        return cls(
            slug=p.slug, name=p.name, source=p.scope, is_active=p.is_active,
            categories=list(p.categories or []), values=dict(p.values or {}),
        )


class PresetListResponse(BaseModel):
    items: list[PresetSummary]


class PresetCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    values: dict[str, Any] = Field(
        ...,
        description="Subset of the caller's flat customization model to "
        "capture. Keys outside ``ALLOWED_CUSTOMIZATION_KEYS`` are dropped; "
        "an empty result is rejected with 400.",
    )


class AdminPresetCreateRequest(PresetCreateRequest):
    is_active: bool = True


class ImportThemesRequest(BaseModel):
    themes: dict[str, dict[str, Any]]
    replace: bool = False


class SetActiveRequest(BaseModel):
    is_active: bool


@router.get(
    "/customization/presets",
    response_model=PresetListResponse,
    summary="List active global presets plus the caller's own.",
)
async def list_presets(
    user: User = Depends(require_user), db: Session = Depends(get_db),
) -> PresetListResponse:
    items = [PresetSummary.of(p) for p in presets_service.list_for_user(db, user.id)]
    return PresetListResponse(items=items)


@router.post(
    "/customization/presets",
    response_model=PresetSummary,
    summary="Save a subset of the current configuration as a personal preset.",
)
async def create_preset(
    payload: PresetCreateRequest,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> PresetSummary:
    """Create a per-user preset (usable across all the caller's scoreboards)."""
    try:
        preset = presets_service.create_user_preset(
            db, user.id, payload.name, payload.values,
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
async def delete_preset(
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
            status_code=403, detail="Global presets are managed by an administrator.",
        )
    raise HTTPException(status_code=404, detail=f"Preset '{slug}' not found.")


# ---- admin global-preset authoring ----------------------------------------


@router.get(
    "/admin/presets", response_model=PresetListResponse,
    summary="List all global presets (active and inactive) for management.",
)
async def admin_list_presets(
    _admin: User = Depends(require_admin), db: Session = Depends(get_db),
) -> PresetListResponse:
    items = [PresetSummary.of(p) for p in presets_service.list_global_presets(db)]
    return PresetListResponse(items=items)


@router.post(
    "/admin/presets", response_model=PresetSummary, status_code=201,
    summary="Author a global preset.",
)
async def admin_create_preset(
    payload: AdminPresetCreateRequest,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> PresetSummary:
    try:
        preset = presets_service.create_global_preset(
            db, payload.name, payload.values, is_active=payload.is_active,
        )
    except presets_service.PresetError as exc:
        detail = str(exc)
        status_code = 409 if "already exists" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from None
    db.commit()
    return PresetSummary.of(preset)


@router.patch("/admin/presets/{slug}", summary="Activate/deactivate a global preset.")
async def admin_set_preset_active(
    body: SetActiveRequest,
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
    "/admin/presets/{slug}", status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a global preset.",
)
async def admin_delete_preset(
    slug: str = Path(..., min_length=1, max_length=120),
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    if not presets_service.delete_global_preset(db, slug):
        raise HTTPException(status_code=404, detail=f"Global preset '{slug}' not found.")
    db.commit()


@router.get("/admin/presets/export", summary="Export global presets as APP_THEMES JSON.")
async def admin_export_presets(
    _admin: User = Depends(require_admin), db: Session = Depends(get_db),
):
    return presets_service.export_app_themes(db)


@router.post("/admin/presets/import", summary="Import an APP_THEMES JSON map.")
async def admin_import_presets(
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
