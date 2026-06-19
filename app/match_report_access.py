"""Access control for the print match-report route ``/match/{id}/report``.

A report can be read three ways:

1. ``MATCH_REPORT_PUBLIC=true`` — open access (anyone with the
   non-guessable ``match_id`` can view it).
2. a valid HMAC capability URL (``?exp=…&sig=…``), minted by the report's
   owner via ``POST /api/v1/matches/{id}/sign-url`` and signed with
   ``SESSION_SECRET`` — no credential on the wire.
3. the report's **owner**, authenticated by their session cookie.
"""

from __future__ import annotations

from fastapi import HTTPException, Request

from app.env_vars_manager import EnvVarsManager
from app.overlay_key import is_valid_skey, split_skey

_WWW_AUTH = {"WWW-Authenticate": "Cookie"}


def _public_mode_enabled() -> bool:
    return EnvVarsManager.get_bool_env("MATCH_REPORT_PUBLIC")


def cookie_user_owns(request: Request, match_id: str | None) -> bool:
    """Whether the request's session cookie belongs to the report's owner."""
    if not match_id:
        return False
    from app.auth import sessions
    from app.db.engine import session_scope

    raw = request.cookies.get(sessions.COOKIE_NAME)
    if not raw:
        return False
    with session_scope() as db:
        user = sessions.resolve_session(db, raw)
        if user is None:
            return False
        from app.api import match_archive

        payload = match_archive.load_match(match_id)
        if payload is None:
            return False
        skey = payload.get("oid")
        if not isinstance(skey, str) or not is_valid_skey(skey):
            return False
        owner_id, _ = split_skey(skey)
        return owner_id == user.id


def check_read_access(
    request: Request,
    match_id: str | None = None,
    *,
    exp: str | None = None,
    sig: str | None = None,
) -> None:
    """Raise ``HTTPException`` unless the caller may read this report."""
    if _public_mode_enabled():
        return
    if match_id is not None and (exp or sig):
        from app.match_report_signing import verify_signed_query

        if verify_signed_query(match_id, exp, sig):
            return
    if cookie_user_owns(request, match_id):
        return
    raise HTTPException(
        status_code=401,
        detail="Sign in as the report's owner, or open it with a shared link.",
        headers=_WWW_AUTH,
    )
