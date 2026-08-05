"""GET /audit — read recent action audit records for a session."""

from typing import Any

from fastapi import APIRouter, Depends, Query

from app.api import action_log
from app.api.dependencies import get_session
from app.api.session_manager import GameSession

router = APIRouter()


@router.get(
    "/audit",
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
) -> dict[str, Any]:
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
    * ``version`` — the log's mutation counter these records were read
      at. Pair it with the ``audit_append`` / ``audit_invalidate``
      WebSocket messages (see FRONTEND_DEVELOPMENT.md) to follow the
      log live instead of re-polling this endpoint.

    ``read_page`` returns the page and the version under one lock hold —
    sampling the counter separately would let a concurrent mutation land
    between the two and hand the caller a page and a version that
    disagree, which a live client resolves into either a duplicated or a
    silently missing record. See its docstring.
    """
    records, next_cursor, version = action_log.read_page(
        session.oid, limit=limit, before_ts=before_ts,
    )
    return {
        "version": version,
        # Present the human-facing oid, never the internal "<user_id>:<oid>"
        # storage key — returning the skey would leak the owner's user_id to
        # any control-link operator (mirrors matches.py ``_present``).
        "oid": session.raw_oid,
        "count": len(records),
        "records": records,
        "next_cursor": next_cursor,
    }
