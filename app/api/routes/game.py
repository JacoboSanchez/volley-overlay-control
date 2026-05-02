"""POST /game/* — game actions (points, sets, timeouts, serve, reset)."""

from fastapi import APIRouter, Depends

from app.api.dependencies import get_session, verify_api_key
from app.api.game_service import GameService
from app.api.schemas import (
    ActionResponse,
    ServeRequest,
    SetScoreRequest,
    SetSetsRequest,
    TeamActionRequest,
)
from app.api.session_manager import GameSession

router = APIRouter()


@router.post(
    "/game/add-point",
    response_model=ActionResponse,
    dependencies=[Depends(verify_api_key)],
)
async def add_point(req: TeamActionRequest,
                    session: GameSession = Depends(get_session)):
    async with session.lock:
        return GameService.add_point(session, req.team, req.undo)


@router.post(
    "/game/add-set",
    response_model=ActionResponse,
    dependencies=[Depends(verify_api_key)],
)
async def add_set(req: TeamActionRequest,
                  session: GameSession = Depends(get_session)):
    async with session.lock:
        return GameService.add_set(session, req.team, req.undo)


@router.post(
    "/game/add-timeout",
    response_model=ActionResponse,
    dependencies=[Depends(verify_api_key)],
)
async def add_timeout(req: TeamActionRequest,
                      session: GameSession = Depends(get_session)):
    async with session.lock:
        return GameService.add_timeout(session, req.team, req.undo)


@router.post(
    "/game/change-serve",
    response_model=ActionResponse,
    dependencies=[Depends(verify_api_key)],
)
async def change_serve(req: ServeRequest,
                       session: GameSession = Depends(get_session)):
    async with session.lock:
        return GameService.change_serve(session, req.team)


@router.post(
    "/game/set-score",
    response_model=ActionResponse,
    dependencies=[Depends(verify_api_key)],
)
async def set_score(req: SetScoreRequest,
                    session: GameSession = Depends(get_session)):
    async with session.lock:
        return GameService.set_score(session, req.team, req.set_number, req.value)


@router.post(
    "/game/set-sets",
    response_model=ActionResponse,
    dependencies=[Depends(verify_api_key)],
)
async def set_sets(req: SetSetsRequest,
                   session: GameSession = Depends(get_session)):
    async with session.lock:
        return GameService.set_sets_value(session, req.team, req.value)


@router.post(
    "/game/reset",
    response_model=ActionResponse,
    dependencies=[Depends(verify_api_key)],
)
async def reset_game(session: GameSession = Depends(get_session)):
    async with session.lock:
        return GameService.reset(session)


@router.post(
    "/game/start-match",
    response_model=ActionResponse,
    dependencies=[Depends(verify_api_key)],
    summary="Arm the match-start timer without scoring a point",
)
async def start_match(session: GameSession = Depends(get_session)):
    """Stamps ``match_started_at`` with the current wallclock if the
    match isn't already armed. Idempotent — a second call leaves the
    original anchor in place. The HUD timer / report duration / undo
    flow all read this field downstream.
    """
    async with session.lock:
        return GameService.start_match(session)


@router.post(
    "/game/undo",
    response_model=ActionResponse,
    dependencies=[Depends(verify_api_key)],
    summary="Reverse the most recent undoable action",
)
async def undo_last(session: GameSession = Depends(get_session)):
    """Pops the most recent forward ``add_point`` / ``add_set`` /
    ``add_timeout`` from the audit log and applies the inverse via
    ``undo=True``. Returns ``success=false`` with message
    ``"Nothing to undo."`` when the log has no eligible entry.
    """
    async with session.lock:
        return GameService.undo_last(session)
