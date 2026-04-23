"""POST /display/* — visibility and simple-mode toggles."""

import logging

from fastapi import APIRouter, Depends

from app.api.dependencies import get_session, verify_api_key
from app.api.game_service import GameService
from app.api.schemas import ActionResponse, SimpleModeRequest, VisibilityRequest
from app.api.session_manager import GameSession

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/display/visibility",
    response_model=ActionResponse,
    dependencies=[Depends(verify_api_key)],
)
async def set_visibility(req: VisibilityRequest,
                         session: GameSession = Depends(get_session)):
    async with session.lock:
        logger.info("Overlay visibility set to %s", req.visible)
        return GameService.set_visibility(session, req.visible)


@router.post(
    "/display/simple-mode",
    response_model=ActionResponse,
    dependencies=[Depends(verify_api_key)],
)
async def set_simple_mode(req: SimpleModeRequest,
                          session: GameSession = Depends(get_session)):
    async with session.lock:
        logger.info("Simple mode set to %s", req.enabled)
        return GameService.set_simple_mode(session, req.enabled)
