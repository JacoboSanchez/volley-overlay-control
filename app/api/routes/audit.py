"""GET /audit — read recent action audit records for a session."""

from fastapi import APIRouter, Depends, Query

from app.api import action_log
from app.api.dependencies import get_session, verify_api_key
from app.api.session_manager import GameSession

router = APIRouter()


@router.get(
    "/audit",
    dependencies=[Depends(verify_api_key)],
    summary="Recent action audit log",
)
async def get_audit_log(
    session: GameSession = Depends(get_session),
    limit: int = Query(100, ge=1, le=1000),
):
    """Return up to *limit* most-recent records from the action log.

    Records are ordered chronologically (oldest first within the
    returned window). Each entry has the shape::

        {"ts": 1714508400.123,
         "action": "add_point",
         "params": {"team": 1, "undo": false},
         "result": {"current_set": 2, "team_1": {...}, ...}}
    """
    records = action_log.read_recent(session.oid, limit=limit)
    return {"oid": session.oid, "count": len(records), "records": records}
