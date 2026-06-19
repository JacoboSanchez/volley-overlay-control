"""Scoreboard API auth + session dependencies (cookie-based).

The legacy ``SCOREBOARD_USERS`` Bearer ladder is gone: every ``/api/v1``
scoreboard route now requires a logged-in user (cookie session), and a
session is addressed by the per-user storage key ``<user_id>:<oid>`` so two
users can drive the same ``oid`` in isolation.

``verify_api_key`` is kept as a name (used as ``dependencies=[Depends(...)]``
on the domain routers) but now simply requires an authenticated, fully
onboarded user — it is an alias for :func:`app.auth.dependencies.require_user`.
"""

import logging

from fastapi import Depends, HTTPException, Query

from app.api.session_manager import GameSession, SessionManager
from app.auth.dependencies import require_user
from app.db.models.user import User
from app.overlay_key import make_skey

logger = logging.getLogger(__name__)

# Route-level "must be logged in" dependency. Named for backwards
# compatibility with the many ``dependencies=[Depends(verify_api_key)]``
# call sites; the implementation is now the cookie-session user gate.
verify_api_key = require_user


async def get_session(
    oid: str | None = Query(None, description="Overlay ID"),
    control: str | None = Query(None, description="Alias of `oid` for backward compatibility"),
    user: User = Depends(require_user),
) -> GameSession:
    """Retrieve the caller's previously-initialised ``GameSession``.

    The session key embeds the authenticated user's id, so a user can only
    ever reach a session they initialised — passing another user's ``oid``
    simply resolves to a different key with no session. Returns 404 when no
    session exists for ``(user, oid)`` (call ``POST /api/v1/session/init``).
    """
    resolved = oid or control
    if not resolved:
        raise HTTPException(
            status_code=422,
            detail="Missing required query parameter: 'oid' (or alias 'control').",
        )

    session = SessionManager.get(make_skey(user.id, resolved))
    if session is None:
        raise HTTPException(
            status_code=404,
            detail=f"No active session for OID '{resolved}'. Call POST /api/v1/session/init first.",
        )
    return session
