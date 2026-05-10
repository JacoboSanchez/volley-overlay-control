"""GET/PUT /customization — team names, colors, logos, theme overrides.

Plus an operator-facing preset CRUD that lives at
``/api/v1/customization/presets/*``: anyone with the API key can list,
save, or delete a named subset of the current customization model.
Apply is intentionally client-side (the React panel deep-merges a
preset's ``values`` into its in-memory edit model and persists with
the existing ``Save`` flow), so the picker UX stays consistent with
direct field edits and never races unsaved changes.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.api import presets_store
from app.api.dependencies import get_session, verify_api_key
from app.api.game_service import GameService
from app.api.schemas import ActionResponse
from app.api.session_manager import GameSession

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
        logger.info("Customization updated (%d keys)", len(data))
        return GameService.update_customization(session, data)


# ---------------------------------------------------------------------------
# Operator-facing preset CRUD
# ---------------------------------------------------------------------------


class PresetSummary(BaseModel):
    slug: str
    name: str
    created_at: float
    categories: list[str] = Field(
        description="Category ids covered by the preset's values "
        "(``team1_name``, ``team1_color``, ``team2_name``, "
        "``team2_color``, ``position``, ``style``).",
    )
    values: dict[str, Any] = Field(
        description="Flat ``ALLOWED_CUSTOMIZATION_KEYS`` patch the "
        "React panel deep-merges into its edit model. Unknown keys "
        "from older records are filtered out at read time.",
    )


class PresetListResponse(BaseModel):
    items: list[PresetSummary]


class PresetCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    values: dict[str, Any] = Field(
        ...,
        description="Subset of the operator's flat customization model "
        "to capture. Keys outside ``ALLOWED_CUSTOMIZATION_KEYS`` are "
        "dropped server-side; an empty result is rejected with 400.",
    )


def _summarize(record: dict) -> PresetSummary:
    meta = record.get("_meta") or {}
    return PresetSummary(
        slug=str(meta.get("slug") or ""),
        name=str(meta.get("name") or meta.get("slug") or ""),
        created_at=float(meta.get("created_at") or 0.0),
        categories=list(record.get("categories") or []),
        values=dict(record.get("values") or {}),
    )


@router.get(
    "/customization/presets",
    response_model=PresetListResponse,
    dependencies=[Depends(verify_api_key)],
    summary="List operator-saved presets.",
)
async def list_presets() -> PresetListResponse:
    """Return every preset on disk, ordered by name (case-insensitive)."""
    records = await run_in_threadpool(presets_store.list_all)
    return PresetListResponse(items=[_summarize(r) for r in records])


@router.post(
    "/customization/presets",
    response_model=PresetSummary,
    dependencies=[Depends(verify_api_key)],
    summary="Save the current configuration (or a subset) as a named preset.",
)
async def create_preset(payload: PresetCreateRequest) -> PresetSummary:
    """Persist *payload.values* under a slugified version of *name*.

    The React panel sends the values directly — it already has the
    operator's flat customization in memory, so the server doesn't
    need to round-trip through ``GameService.refresh_customization``.
    """
    try:
        record = await run_in_threadpool(
            presets_store.create, payload.name, payload.values,
        )
    except presets_store.PresetExists as exc:
        raise HTTPException(
            status_code=409,
            detail=f"Preset '{exc!s}' already exists.",
        ) from None
    except presets_store.PresetCatalogueFull as exc:
        raise HTTPException(status_code=507, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return _summarize(record)


@router.delete(
    "/customization/presets/{slug}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(verify_api_key)],
    summary="Delete an operator-saved preset.",
)
async def delete_preset(
    slug: str = Path(..., min_length=1, max_length=120),
) -> None:
    removed = await run_in_threadpool(presets_store.delete, slug)
    if not removed:
        raise HTTPException(
            status_code=404, detail=f"Preset '{slug}' not found.",
        )
