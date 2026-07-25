"""GET /state, /config — read-only session queries."""

from fastapi import APIRouter, Depends
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import get_session
from app.api.game_service import GameService
from app.api.schemas import GameStateResponse
from app.api.session_manager import GameSession

router = APIRouter()


@router.get(
    "/state",
    response_model=GameStateResponse,
)
async def get_state(session: GameSession = Depends(get_session)):
    # ``get_state`` reads the audit log and aggregates live stats — real
    # blocking work, and this endpoint is polled. Keep it off the loop.
    return await run_in_threadpool(GameService.get_state, session)


@router.get("/config")
async def get_config(session: GameSession = Depends(get_session)):
    return {
        "points_limit": session.points_limit,
        "points_limit_last_set": session.points_limit_last_set,
        "sets_limit": session.sets_limit,
    }
