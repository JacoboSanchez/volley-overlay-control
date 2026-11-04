"""GET /audit — read recent action audit records for a session."""

from functools import partial
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.concurrency import run_in_threadpool

from app.api import action_log
from app.api.audit_replay import check_consistency
from app.api.dependencies import get_session
from app.api.schemas import AuditConsistencyResponse
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

    Returns **503** when the log cannot be read. That is deliberate
    rather than an empty page: an empty page carrying a live version
    would tell a following client "you are up to date at N" about
    records it never received.

    ``read_page`` returns the page and the version under one lock hold —
    sampling the counter separately would let a concurrent mutation land
    between the two and hand the caller a page and a version that
    disagree, which a live client resolves into either a duplicated or a
    silently missing record. See its docstring.
    """
    records, next_cursor, version = action_log.read_page(
        session.oid, limit=limit, before_ts=before_ts,
    )
    if version is None:
        # The read failed. Returning its empty page with the live counter
        # would be the most damaging answer available: the counter
        # accounts for every record the caller did not get, so a client
        # following the log would treat the next append as contiguous,
        # build on an empty history and never see a gap to recover from.
        # A retryable error leaves the client's existing failure path to
        # clear its copy and re-read.
        raise HTTPException(
            status_code=503,
            detail="Audit log is temporarily unreadable.",
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


@router.get(
    "/audit/consistency",
    response_model=AuditConsistencyResponse,
    summary="Check the live match state against a replay of the audit log",
)
async def get_audit_consistency(
    session: GameSession = Depends(get_session),
) -> dict[str, Any]:
    """Rebuild the match from the audit log and compare it with live state.

    Every mutation records a post-state snapshot, so folding the visible
    (tombstone-filtered) history must reproduce the scoreboard. A
    divergence means an audit append failed or a mutation path skipped the
    log; the response names each disagreeing field. Sets the surviving
    history never scored in (retention pruning, or not yet played) are left
    out of ``covered_sets`` and never reported as divergent.

    The log and the state are sampled under ``session.lock`` — the lock
    every mutation holds — so a point scored mid-check cannot show up in one
    and not the other. Returns **503** when the log cannot be read.
    """
    async with session.lock:
        # A cold read hits the runtime database; keep it off the event loop.
        records, _, version = await run_in_threadpool(
            action_log.read_page, session.oid, 1_000_000_000,
        )
        live = session.game_manager.get_current_state().copy()
        # Table tennis derives the serve in ``get_state`` after the audit
        # snapshot is taken, so a recorded serve is not meaningful there.
        compare_serve = session.mode != "table_tennis"
    if version is None:
        raise HTTPException(
            status_code=503,
            detail="Audit log is temporarily unreadable.",
        )
    # The fold is pure CPU over the whole history; keep it off the loop.
    return await run_in_threadpool(
        partial(check_consistency, records, live, compare_serve=compare_serve),
    )
