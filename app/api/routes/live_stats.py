"""GET /matches/live/stats — live match statistics derived from audit."""

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_session, verify_api_key
from app.api.live_stats import compute_live_stats
from app.api.session_manager import GameSession

router = APIRouter()


@router.get(
    "/matches/live/stats",
    dependencies=[Depends(verify_api_key)],
    summary="Live match statistics for the active session",
)
async def get_live_stats(
    session: GameSession = Depends(get_session),
    limit: int = Query(
        30,
        ge=0,
        le=200,
        description="Maximum number of recent points returned in ``points_history``.",
    ),
):
    """Return rolling stats computed from the per-OID audit log.

    The payload reconciles with the post-match report so external
    consumers (overlay viewer page, coach apps, dashboards) can render
    the same Highlights block while the match is still in progress.

    Fields:

    * ``current_streak`` — trailing run by one team
      (``{"team": 1, "n": 4, "set": 2}``).
    * ``longest_streak`` — longest run across the whole match so far.
    * ``set_win_comeback`` / ``partial_comeback`` — per-team peak
      deficits, same semantics as the printed match report.
    * ``longest_rally`` — gap in seconds between consecutive points
      (proxy for "longest rally" — no ball-tracking).
    * ``total_points`` — total points scored across all sets.
    * ``set_durations`` — per-set duration in seconds.
    * ``points_history`` — last ``limit`` scoring events with the
      running score after each one.
    * ``audit_count`` — cache-buster derived from the audit log size.
    """
    return compute_live_stats(session.oid, history_limit=limit)
