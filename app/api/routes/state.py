"""GET /state, /config — read-only session queries."""

from fastapi import APIRouter, Depends

from app.api.dependencies import get_session, verify_api_key
from app.api.game_service import GameService
from app.api.schemas import GameStateResponse
from app.api.session_manager import GameSession

router = APIRouter()


@router.get(
    "/state",
    response_model=GameStateResponse,
    dependencies=[Depends(verify_api_key)],
)
async def get_state(session: GameSession = Depends(get_session)):
    return GameService.get_state(session)


@router.get("/config", dependencies=[Depends(verify_api_key)])
async def get_config(session: GameSession = Depends(get_session)):
    return {
        "points_limit": session.points_limit,
        "points_limit_last_set": session.points_limit_last_set,
        "sets_limit": session.sets_limit,
    }
