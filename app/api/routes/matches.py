"""GET /matches, /matches/{match_id} — read the caller's archived matches.

Archives are stored per-user (keyed by ``<user_id>:<oid>``); these routes
scope every listing/lookup to the authenticated user and present the
human-facing ``oid`` (never the internal storage key) in responses.
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api import match_archive
from app.auth.dependencies import require_user
from app.db.models.user import User
from app.overlay_key import is_valid_skey, make_skey, split_skey

router = APIRouter()


def _present(summary: dict) -> dict:
    """Return a copy with the storage-key ``oid`` mapped to the raw oid."""
    out = dict(summary)
    skey = out.get("oid")
    if isinstance(skey, str) and is_valid_skey(skey):
        out["oid"] = split_skey(skey)[1]
    return out


def _owns(skey: object, user: User) -> bool:
    return isinstance(skey, str) and skey.startswith(f"{user.id}:")


@router.get("/matches", summary="List the caller's archived matches")
async def list_matches(
    oid: str | None = Query(None, description="Filter to a single overlay id"),
    user: User = Depends(require_user),
):
    """Return summaries of the caller's archived matches, newest first."""
    # Always enforce ownership in the route: never trust ``list_matches`` to
    # scope by the storage key. A malformed ``oid`` makes ``make_skey`` produce
    # an invalid key, and ``list_matches`` then fails *open* (returns the full
    # cross-user index) — so the ``_owns`` filter is the real authorization gate.
    raw = match_archive.list_matches(oid=make_skey(user.id, oid)) if oid \
        else match_archive.list_matches()
    summaries = [s for s in raw if _owns(s.get("oid"), user)]
    return {"count": len(summaries), "matches": [_present(s) for s in summaries]}


@router.get("/matches/{match_id}", summary="Full archived match snapshot")
async def get_match(match_id: str, user: User = Depends(require_user)):
    payload = match_archive.load_match(match_id)
    if payload is None or not _owns(payload.get("oid"), user):
        raise HTTPException(status_code=404, detail="Match not found.")
    return _present(payload)
