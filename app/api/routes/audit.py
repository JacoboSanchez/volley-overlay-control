"""GET /audit — read recent action audit records for a session."""

from fastapi import APIRouter, Depends, Query

from app.api import action_log
from app.api.dependencies import get_session, verify_api_key
from app.api.session_manager import GameSession

router = APIRouter()


@router.get(
    "/audit",
    dependencies=[Depends(verify_api_key)],
    summary="Recent action audit log (cursor-paginated)",
)
async def get_audit_log(
    session: GameSession = Depends(get_session),
    limit: int = Query(100, ge=1, le=1000),
    before_ts: float | None = Query(
        None,
        description=(
            "Pagination cursor: only return records strictly older "
            "than this timestamp. Use the ``next_cursor`` value from "
            "the previous response. Omit for the first page."
        ),
    ),
):
    """Return one page of audit records, newest page first.

    First call (``before_ts`` omitted) returns the most recent
    ``limit`` records. Subsequent calls pass the previous response's
    ``next_cursor`` to walk back through history one window at a time.

    Records are ordered chronologically (oldest first **within** the
    returned window — same convention as ``read_recent``). Each entry
    has the shape::

        {"ts": 1714508400.123,
         "action": "add_point",
         "params": {"team": 1, "undo": false},
         "result": {"current_set": 2, "team_1": {...}, ...}}

    The response carries:

    * ``records`` — the page itself.
    * ``count`` — ``len(records)``.
    * ``next_cursor`` — the ``ts`` to pass as ``before_ts`` for the
      next page, or ``null`` when this is the last page.
    """
    records, next_cursor = action_log.read_page(
        session.oid, limit=limit, before_ts=before_ts,
    )
    return {
        # Present the human-facing oid, never the internal "<user_id>:<oid>"
        # storage key — returning the skey would leak the owner's user_id to
        # any control-link operator (mirrors matches.py ``_present``).
        "oid": session.raw_oid,
        "count": len(records),
        "records": records,
        "next_cursor": next_cursor,
    }
