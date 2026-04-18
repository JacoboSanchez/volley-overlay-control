"""GET/PUT /customization — team names, colors, logos, theme overrides."""

from fastapi import APIRouter, Depends
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import get_session, verify_api_key
from app.api.game_service import GameService
from app.api.schemas import ActionResponse
from app.api.session_manager import GameSession

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
        return GameService.update_customization(session, data)
