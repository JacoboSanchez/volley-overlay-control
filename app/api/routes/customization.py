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

import json
import logging
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.api import presets_store
from app.api.dependencies import get_session, verify_api_key
from app.api.game_service import GameService
from app.api.preset_categories import categories_for_keys, filter_to_known
from app.api.schemas import ActionResponse
from app.api.session_manager import GameSession
from app.env_vars_manager import EnvVarsManager

logger = logging.getLogger(__name__)
router = APIRouter()


# Tracks the raw ``APP_THEMES`` value we last logged a parse failure
# for. ``_system_presets`` runs on every preset-list request, so a
# malformed env var would otherwise spam the warning every poll. We
# only emit the warning when the value changes (so an operator who
# fixes the JSON, or swaps in a new mistake, still gets feedback).
_last_logged_malformed_app_themes: str | None = None


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
    source: Literal["user", "system"] = Field(
        "user",
        description="``user`` for operator-saved records on disk; "
        "``system`` for read-only entries derived from ``APP_THEMES``. "
        "System presets cannot be deleted.",
    )
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
        source="user",
        categories=list(record.get("categories") or []),
        values=dict(record.get("values") or {}),
    )


def _system_presets() -> list[PresetSummary]:
    """Map ``APP_THEMES`` to read-only ``PresetSummary`` records.

    Reads the env var directly (rather than via ``Customization.THEMES``)
    so test reloads of ``app.customization`` cannot leave us holding a
    stale class reference. Malformed JSON logs a warning at most once
    per distinct value (see ``_last_logged_malformed_app_themes``);
    theme names that yield an empty slug or have no allow-listed
    values are skipped silently. ``slugify`` is called with
    ``check_reserved=False`` because the loader prepends the reserved
    prefix unconditionally, so a theme literally named "System Dark"
    addresses as ``system-system-dark`` instead of being dropped.
    """
    global _last_logged_malformed_app_themes
    raw_json = EnvVarsManager.get_env_var("APP_THEMES", None)
    if not raw_json:
        return []
    try:
        themes = json.loads(raw_json)
    except json.JSONDecodeError:
        if _last_logged_malformed_app_themes != raw_json:
            logger.warning("Malformed APP_THEMES env var; ignoring value")
            _last_logged_malformed_app_themes = raw_json
        return []
    if not isinstance(themes, dict):
        return []
    items: list[PresetSummary] = []
    for name, raw in themes.items():
        if not isinstance(raw, dict):
            continue
        cleaned = filter_to_known(raw)
        if not cleaned:
            continue
        try:
            base_slug = presets_store.slugify(str(name), check_reserved=False)
        except ValueError:
            continue
        items.append(
            PresetSummary(
                slug=f"{presets_store.SYSTEM_SLUG_PREFIX}{base_slug}",
                name=str(name),
                created_at=0.0,
                source="system",
                categories=categories_for_keys(cleaned.keys()),
                values=cleaned,
            ),
        )
    items.sort(key=lambda p: p.name.lower())
    return items


@router.get(
    "/customization/presets",
    response_model=PresetListResponse,
    dependencies=[Depends(verify_api_key)],
    summary="List operator-saved and system presets.",
)
async def list_presets() -> PresetListResponse:
    """Return every preset, ordered system-first then by name.

    System entries are derived from ``APP_THEMES`` at request time and
    are not persisted; user entries come from disk. Both share the same
    ``PresetSummary`` shape so the React picker can render them in a
    single list.
    """
    records = await run_in_threadpool(presets_store.list_all)
    user_items = [_summarize(r) for r in records]
    user_items.sort(key=lambda p: p.name.lower())
    system_items = await run_in_threadpool(_system_presets)
    return PresetListResponse(items=system_items + user_items)


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
    if slug.startswith(presets_store.SYSTEM_SLUG_PREFIX):
        raise HTTPException(
            status_code=403,
            detail="System presets cannot be deleted.",
        )
    removed = await run_in_threadpool(presets_store.delete, slug)
    if not removed:
        raise HTTPException(
            status_code=404, detail=f"Preset '{slug}' not found.",
        )
