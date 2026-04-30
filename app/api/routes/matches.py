"""GET /matches, /matches/{match_id} — read archived match snapshots."""

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api import match_archive
from app.api.dependencies import verify_api_key

router = APIRouter()


@router.get(
    "/matches",
    dependencies=[Depends(verify_api_key)],
    summary="List archived matches",
)
async def list_matches(
    oid: str | None = Query(None, description="Filter to a single OID"),
):
    """Return summaries of archived matches, newest first.

    Each entry is enough to render a list view: ``match_id``, ``oid``,
    ``ended_at``, ``duration_s``, ``winning_team``, plus the team-level
    sets-won and ``current_set``. Use ``GET /matches/{match_id}`` for
    the full snapshot including the audit log and customization.
    """
    summaries = match_archive.list_matches(oid=oid)
    return {"count": len(summaries), "matches": summaries}


@router.get(
    "/matches/{match_id}",
    dependencies=[Depends(verify_api_key)],
    summary="Full archived match snapshot",
)
async def get_match(match_id: str):
    payload = match_archive.load_match(match_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Match not found.")
    return payload
