"""POST /game/* — game actions (points, sets, timeouts, serve, reset).

Every handler hands ``GameService`` to ``run_in_threadpool``: the action
path writes the overlay state to disk, persists session meta and submits
background work to the bounded overlay executor, whose backpressure
blocks until a slot frees. None of that may run on the event-loop
thread — see ``app/overlay_executor.py`` and the "Do not block the event
loop" pitfall in AGENTS.md. ``get_mutation_session`` still holds the
board's asyncio lock across the hop, so mutations stay serialized.
"""

from fastapi import APIRouter, Depends
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import get_mutation_session
from app.api.game_service import GameService
from app.api.schemas import (
    ActionResponse,
    AddPointRequest,
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
)
async def add_point(req: AddPointRequest,
                    session: GameSession = Depends(get_mutation_session)) -> ActionResponse:
    return await run_in_threadpool(
        GameService.add_point,
        session, req.team, req.undo,
        point_type=req.point_type, error_type=req.error_type,
    )


@router.post(
    "/game/add-set",
    response_model=ActionResponse,
)
async def add_set(req: TeamActionRequest,
                  session: GameSession = Depends(get_mutation_session)) -> ActionResponse:
    return await run_in_threadpool(GameService.add_set, session, req.team, req.undo)


@router.post(
    "/game/add-timeout",
    response_model=ActionResponse,
)
async def add_timeout(req: TeamActionRequest,
                      session: GameSession = Depends(get_mutation_session)) -> ActionResponse:
    return await run_in_threadpool(GameService.add_timeout, session, req.team, req.undo)


@router.post(
    "/game/change-serve",
    response_model=ActionResponse,
)
async def change_serve(req: ServeRequest,
                       session: GameSession = Depends(get_mutation_session)) -> ActionResponse:
    return await run_in_threadpool(GameService.change_serve, session, req.team)


@router.post(
    "/game/set-score",
    response_model=ActionResponse,
)
async def set_score(req: SetScoreRequest,
                    session: GameSession = Depends(get_mutation_session)) -> ActionResponse:
    return await run_in_threadpool(
        GameService.set_score, session, req.team, req.set_number, req.value,
    )


@router.post(
    "/game/set-sets",
    response_model=ActionResponse,
)
async def set_sets(req: SetSetsRequest,
                   session: GameSession = Depends(get_mutation_session)) -> ActionResponse:
    return await run_in_threadpool(GameService.set_sets_value, session, req.team, req.value)


@router.post(
    "/game/reset",
    response_model=ActionResponse,
)
async def reset_game(session: GameSession = Depends(get_mutation_session)) -> ActionResponse:
    return await run_in_threadpool(GameService.reset, session)


@router.post(
    "/game/start-match",
    response_model=ActionResponse,
    summary="Arm the match-start timer without scoring a point",
)
async def start_match(session: GameSession = Depends(get_mutation_session)) -> ActionResponse:
    """Stamps ``match_started_at`` with the current wallclock if the
    match isn't already armed. Idempotent — a second call leaves the
    original anchor in place. The HUD timer / report duration / undo
    flow all read this field downstream.
    """
    return await run_in_threadpool(GameService.start_match, session)


@router.post(
    "/game/undo",
    response_model=ActionResponse,
    summary="Reverse the most recent undoable action",
)
async def undo_last(session: GameSession = Depends(get_mutation_session)) -> ActionResponse:
    """Pops the most recent forward ``add_point`` / ``add_set`` /
    ``add_timeout`` from the audit log and applies the inverse via
    ``undo=True``. Returns ``success=false`` with message
    ``"Nothing to undo."`` when the log has no eligible entry.
    """
    return await run_in_threadpool(GameService.undo_last, session)
