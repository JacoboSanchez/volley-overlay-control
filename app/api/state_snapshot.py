"""Consistent state presentation for asynchronous control routes."""

from starlette.concurrency import run_in_threadpool

from app.api.game_service import GameService
from app.api.schemas import GameStateResponse
from app.api.session_manager import GameSession


async def get_state_snapshot(session: GameSession) -> GameStateResponse:
    """Build one state response while excluding concurrent mutations.

    ``GameService.get_state`` can persist a newly observed revision, so it
    belongs in the worker pool. The session lock must remain owned by the
    event-loop task around that worker call: otherwise the presenter can read
    half of a mutation and fingerprint an inconsistent intermediate state.
    """
    async with session.lock:
        return await run_in_threadpool(GameService.get_state, session)
