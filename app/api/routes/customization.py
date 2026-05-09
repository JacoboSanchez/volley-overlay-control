"""GET/PUT /customization — team names, colors, logos, theme overrides."""

import logging
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.api import preset_translation, presets_store
from app.api.dependencies import get_session, verify_api_key
from app.api.game_service import GameService
from app.api.schemas import ActionResponse
from app.api.session_manager import GameSession

logger = logging.getLogger(__name__)


def _customization_class():
    # ``test_customization.py`` reloads the ``app.customization`` module
    # via ``importlib.reload``. A module-level ``from app.customization
    # import Customization`` would freeze a stale class reference past
    # that reload, leaving our ``THEMES`` lookup pointing at an empty
    # singleton in the rest of the test session. Resolving the class
    # through the module on every call survives the reload.
    import app.customization as _cust
    return _cust.Customization
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
# Operator-facing preset surface
# ---------------------------------------------------------------------------
#
# Admin-only preset CRUD continues to live under ``/api/v1/admin/presets/*``
# (see :mod:`app.admin.routes`). The route below is the read-only
# counterpart for the React control panel: an operator with the API key
# lists applicable presets (env-var ``APP_THEMES`` + admin-curated user
# presets, mixed in one feed with a ``read_only`` marker) and the patch
# payload that the panel can deep-merge into its in-memory edit model.
#
# Apply is intentionally client-side: the panel already stages user
# edits in its local ``model`` state and persists everything via the
# existing ``PUT /customization`` save flow. Wiring a separate
# server-side apply endpoint would diverge from that "stage then save"
# UX (the operator could lose unsaved edits to an immediate apply, and
# would now need to know whether each control writes through or not).
# Returning the precomputed patch alongside the list keeps the existing
# theme-dropdown semantics intact and eliminates a second round-trip.


class PresetOptionItem(BaseModel):
    source: str = Field(
        description="``env`` for env-var ``APP_THEMES``, ``user`` for "
        "admin-curated presets persisted in ``data/presets/``.",
    )
    id: str = Field(
        description="Stable identifier — ``theme:<key>`` for env themes, "
        "``preset:<slug>`` for user presets.",
    )
    name: str
    scopes: list[str] = Field(
        description="Scopes the patch covers. Synthesised for env themes "
        "(``overlay_colors`` since they always carry colour keys); the "
        "subset of the record's own scopes that translated to non-empty "
        "flat-key writes for user presets.",
    )
    patch: dict[str, Any] = Field(
        description="Flat ``ALLOWED_CUSTOMIZATION_KEYS`` patch the React "
        "panel deep-merges into its edit model. Empty patches are "
        "filtered before the response is built.",
    )
    read_only: bool = Field(
        description="``true`` when the operator cannot manage this entry "
        "(env-var themes need a backend restart to change).",
    )


class PresetOptionsResponse(BaseModel):
    items: list[PresetOptionItem]


def _theme_options() -> list[PresetOptionItem]:
    cust = _customization_class()
    cust.refresh()
    items: list[PresetOptionItem] = []
    for key, payload in cust.THEMES.items():
        if not isinstance(key, str) or not key:
            continue
        if not isinstance(payload, dict) or not payload:
            continue
        items.append(
            PresetOptionItem(
                source="env",
                id=f"theme:{key}",
                name=key,
                # Env-var themes are paint-only patches; surface that
                # under the same scope label the user-preset side uses
                # so the operator's "this changes colours" mental model
                # holds across both sources.
                scopes=["overlay_colors"],
                patch=dict(payload),
                read_only=True,
            ),
        )
    items.sort(key=lambda i: i.name.lower())
    return items


def _user_preset_options() -> list[PresetOptionItem]:
    items: list[PresetOptionItem] = []
    for record in presets_store.list_all():
        meta = record.get("_meta") or {}
        slug = meta.get("slug")
        name = meta.get("name") or slug
        if not isinstance(slug, str) or not slug:
            continue
        patch, applied = preset_translation.translate_record(record)
        if not patch:
            # Preset captured nested keys with no flat counterpart
            # (e.g. team_home.short_name only). Hide it from the
            # operator's list rather than offer a no-op apply.
            continue
        items.append(
            PresetOptionItem(
                source="user",
                id=f"preset:{slug}",
                name=str(name),
                scopes=applied,
                patch=patch,
                read_only=False,
            ),
        )
    return items


@router.get(
    "/customization/preset-options",
    response_model=PresetOptionsResponse,
    dependencies=[Depends(verify_api_key)],
    summary="List presets and themes the operator can apply to the panel.",
)
async def list_preset_options() -> PresetOptionsResponse:
    """Return env-var themes + user presets in a single feed.

    Each item carries the flat-key patch the operator's React panel
    deep-merges into its in-memory edit model — no second round-trip
    is needed to apply. Snapshots from the original preset record are
    intentionally not surfaced here; they remain admin-only via
    ``GET /api/v1/admin/presets/{slug}``.
    """
    user_items = await run_in_threadpool(_user_preset_options)
    items = _theme_options() + user_items
    return PresetOptionsResponse(items=items)
