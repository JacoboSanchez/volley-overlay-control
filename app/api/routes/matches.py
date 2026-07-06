"""GET /matches, /matches/{match_id} — read the caller's archived matches.

Archives are stored per-user (keyed by ``<user_id>:<oid>``); these routes
scope every listing/lookup to the authenticated user and present the
human-facing ``oid`` (never the internal storage key) in responses.
"""

import time

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api import match_archive
from app.auth.dependencies import require_user
from app.db.models.user import User
from app.match_report_signing import make_signed_query
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
def list_matches(
    oid: str | None = Query(None, description="Filter to a single overlay id"),
    limit: int = Query(100, ge=1, le=500, description="Page size"),
    offset: int = Query(0, ge=0, description="Rows to skip (newest first)"),
    user: User = Depends(require_user),
):
    """Return a page of the caller's archived matches, newest first.

    ``count`` is the total in scope (not the page length), so a client can
    page with ``offset``/``limit`` until it has everything.
    """
    # The ``_owns`` filter below is the real authorization gate, applied
    # unconditionally to every branch. Note the two ``list_matches`` shapes:
    # a provided ``oid`` is scoped to this user's skey and fails *closed* on a
    # malformed key (returns ``[]``); the no-``oid`` branch pushes the
    # ``user_id`` predicate into SQL (defense-in-depth then narrows it).
    # Either way the caller only ever sees rows whose skey starts with
    # ``"<their id>:"``.
    skey = make_skey(user.id, oid) if oid else None
    raw = match_archive.list_matches(
        oid=skey, user_id=None if oid else user.id, limit=limit, offset=offset,
    )
    total = match_archive.count_matches(oid=skey, user_id=None if oid else user.id)
    summaries = [s for s in raw if _owns(s.get("oid"), user)]
    return {
        "count": total,
        "matches": [_present(s) for s in summaries],
        "limit": limit,
        "offset": offset,
    }


@router.get("/matches/{match_id}", summary="Full archived match snapshot")
def get_match(match_id: str, user: User = Depends(require_user)):
    payload = match_archive.load_match(match_id)
    if payload is None or not _owns(payload.get("oid"), user):
        raise HTTPException(status_code=404, detail="Match not found.")
    return _present(payload)


@router.delete("/matches/{match_id}", status_code=204, summary="Delete one of the caller's matches")
def delete_match(match_id: str, user: User = Depends(require_user)):
    payload = match_archive.load_match(match_id)
    if payload is None or not _owns(payload.get("oid"), user):
        raise HTTPException(status_code=404, detail="Match not found.")
    match_archive.delete_match(match_id)


@router.post("/matches/{match_id}/sign-url", summary="Mint a shareable signed report URL")
def sign_match_url(
    match_id: str,
    request: Request,
    ttl_seconds: int | None = Query(None, description="URL lifetime in seconds."),
    user: User = Depends(require_user),
):
    """Return a short-lived capability URL for the caller's own match report.

    The URL embeds an HMAC signature (key: SESSION_SECRET), so it can be
    shared without the recipient signing in — and without leaking any
    credential. Only the report's owner may mint one.
    """
    payload = match_archive.load_match(match_id)
    if payload is None or not _owns(payload.get("oid"), user):
        raise HTTPException(status_code=404, detail="Match not found.")
    signed = make_signed_query(match_id, ttl_seconds)
    if signed is None:  # pragma: no cover - SESSION_SECRET is always set
        raise HTTPException(status_code=503, detail="Report signing is unavailable.")
    base = str(request.base_url).rstrip("/")
    return {
        "url": f"{base}/match/{match_id}/report?exp={signed['exp']}&sig={signed['sig']}",
        "expires_at": signed["expires_at"],
        "expires_in": max(0, signed["expires_at"] - int(time.time())),
    }
