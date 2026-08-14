"""POST /display/* — visibility and simple-mode toggles.

Handlers hop to a worker thread for the same reason the game actions do
(see ``app/api/routes/game.py``): the display toggles persist state and
push overlay work through the bounded executor, whose backpressure must
never block the event loop.
"""

import logging

from fastapi import APIRouter, Depends
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import get_mutation_session
from app.api.game_service import GameService
from app.api.schemas import (
    ActionResponse,
    AutoSwapSidesRequest,
    SetSummaryRequest,
    SetSummaryStyleRequest,
    SimpleModeRequest,
    SwapSidesRequest,
    VisibilityRequest,
)
from app.api.session_manager import GameSession

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/display/visibility",
    response_model=ActionResponse,
)
async def set_visibility(req: VisibilityRequest,
                         session: GameSession = Depends(get_mutation_session)) -> ActionResponse:
    logger.debug("Overlay visibility set to %s", req.visible)
    return await run_in_threadpool(GameService.set_visibility, session, req.visible)


@router.post(
    "/display/simple-mode",
    response_model=ActionResponse,
)
async def set_simple_mode(req: SimpleModeRequest,
                          session: GameSession = Depends(get_mutation_session)) -> ActionResponse:
    logger.debug("Simple mode set to %s", req.enabled)
    return await run_in_threadpool(GameService.set_simple_mode, session, req.enabled)


@router.post(
    "/display/swap-sides",
    response_model=ActionResponse,
)
async def set_swap_sides(req: SwapSidesRequest,
                         session: GameSession = Depends(get_mutation_session)) -> ActionResponse:
    """Set the effective display orientation (True = team 2 left)."""
    logger.debug("Sides swapped set to %s", req.swapped)
    return await run_in_threadpool(GameService.set_sides_swapped, session, req.swapped)


@router.post(
    "/display/auto-swap-sides",
    response_model=ActionResponse,
)
async def set_auto_swap_sides(req: AutoSwapSidesRequest,
                              session: GameSession = Depends(get_mutation_session)) -> ActionResponse:
    """Toggle automatic side swapping (set changes + mid-set points)."""
    logger.debug("Auto swap sides set to %s", req.enabled)
    return await run_in_threadpool(GameService.set_auto_swap_sides, session, req.enabled)


@router.post(
    "/display/set-summary",
    response_model=ActionResponse,
)
async def set_set_summary(req: SetSummaryRequest,
                          session: GameSession = Depends(get_mutation_session)) -> ActionResponse:
    """Toggle the set-summary overlay panel on/off."""
    logger.debug("Set summary mode set to %s", req.enabled)
    return await run_in_threadpool(GameService.set_set_summary_mode, session, req.enabled)


@router.post(
    "/display/set-summary-style",
    response_model=ActionResponse,
)
async def set_set_summary_style(req: SetSummaryStyleRequest,
                                session: GameSession = Depends(get_mutation_session)) -> ActionResponse:
    """Pick the visual variant for the set-summary overlay."""
    logger.debug("Set summary style set to %s", req.style)
    return await run_in_threadpool(GameService.set_set_summary_style, session, req.style)
