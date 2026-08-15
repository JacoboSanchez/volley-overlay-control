"""GET /state, /config — read-only session queries."""

from fastapi import APIRouter, Depends

from app.api.dependencies import get_session
from app.api.schemas import GameStateResponse
from app.api.session_manager import GameSession
from app.api.state_snapshot import get_state_snapshot

router = APIRouter()


@router.get(
    "/state",
    response_model=GameStateResponse,
)
async def get_state(
    session: GameSession = Depends(get_session),
) -> GameStateResponse:
    return await get_state_snapshot(session)


@router.get("/config")
async def get_config(
    session: GameSession = Depends(get_session),
) -> dict[str, int]:
    # ``POST /session/rules`` applies a preset one field at a time from a
    # worker thread while holding ``session.lock``. Reading the limits
    # without that lock can interleave between those assignments and hand a
    # legacy client a mixture of the old and new preset, so hold it for the
    # whole snapshot. No docstring: FastAPI would publish it as the public
    # endpoint description.
    async with session.lock:
        return {
            "points_limit": session.points_limit,
            "points_limit_last_set": session.points_limit_last_set,
            "sets_limit": session.sets_limit,
        }
