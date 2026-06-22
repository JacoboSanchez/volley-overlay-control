"""Scoreboard API auth + session dependencies.

The control board is reachable two ways:

* **Owner** — a logged-in cookie session (`vsession`). The session is addressed
  by the per-user storage key ``<user_id>:<oid>`` so two users can drive the
  same ``oid`` in isolation.
* **Operator** — an unguessable *control token* passed as ``?c=<token>`` (or the
  ``X-Control-Token`` header). The token resolves to one overlay's storage key,
  granting full board control without a login — the link an owner hands to
  whoever is running the match. It also separates two users sharing an ``oid``.

``verify_api_key`` is kept as a name (used as ``dependencies=[Depends(...)]`` on
the domain routers); it now authorizes *either* a valid control token or an
onboarded cookie user. ``get_session`` resolves the storage key from whichever
credential is present.
"""

import logging

from fastapi import Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from app import overlays_service
from app.api.session_manager import GameSession, SessionManager
from app.auth.dependencies import PASSWORD_CHANGE_REQUIRED, current_user
from app.db.engine import get_db
from app.db.models.user import User
from app.overlay_key import make_skey

logger = logging.getLogger(__name__)

_WWW_AUTH = {"WWW-Authenticate": "Cookie"}
_INVALID_LINK = "Invalid or revoked control link."


def control_token(
    c: str | None = Query(None, description="Control capability token (shareable board link)"),
    x_control_token: str | None = Header(None, description="Control capability token (alternative to ?c=)"),
) -> str | None:
    """The control token from the ``?c=`` query or ``X-Control-Token`` header."""
    return c or x_control_token


def _require_onboarded(user: User | None) -> None:
    """Raise unless *user* is an authenticated, password-current account."""
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated.", headers=_WWW_AUTH)
    if user.must_change_password:
        raise HTTPException(status_code=409, detail=PASSWORD_CHANGE_REQUIRED)


def resolve_board_skey(
    db: Session,
    *,
    token: str | None,
    user: User | None,
    oid: str | None,
) -> str:
    """Resolve the storage key for the board, from a control token or cookie.

    A valid control token wins and needs no login. Otherwise the caller must be
    an onboarded user and pass an ``oid``.
    """
    if token:
        overlay = overlays_service.get_by_control_token(db, token)
        if overlay is None:
            raise HTTPException(status_code=403, detail=_INVALID_LINK)
        return overlays_service.skey_for(overlay)

    _require_onboarded(user)
    if not oid:
        raise HTTPException(
            status_code=422,
            detail="Missing required query parameter: 'oid' (or alias 'control').",
        )
    return make_skey(user.id, oid)  # type: ignore[union-attr]  # _require_onboarded ensures non-None


async def require_board_control(
    token: str | None = Depends(control_token),
    user: User | None = Depends(current_user),
    db: Session = Depends(get_db),
) -> None:
    """Authorize a board-control request: valid control token OR onboarded user.

    Pure gate (no return value) — used as ``dependencies=[Depends(...)]``.
    """
    if token:
        if overlays_service.get_by_control_token(db, token) is None:
            raise HTTPException(status_code=403, detail=_INVALID_LINK)
        return
    _require_onboarded(user)


# Route-level "may control this board" dependency. Named for backwards
# compatibility with the many ``dependencies=[Depends(verify_api_key)]`` call
# sites; the implementation is now the token-or-cookie board gate.
verify_api_key = require_board_control


async def get_session(
    oid: str | None = Query(None, description="Overlay ID"),
    control: str | None = Query(None, description="Alias of `oid` for backward compatibility"),
    token: str | None = Depends(control_token),
    user: User | None = Depends(current_user),
    db: Session = Depends(get_db),
) -> GameSession:
    """Retrieve the board's previously-initialised ``GameSession``.

    The storage key comes from the control token (operator) or the cookie user +
    ``oid`` (owner), so a caller only ever reaches the board their credential
    authorizes. Returns 404 when no session exists (call
    ``POST /api/v1/session/init`` first).
    """
    skey = resolve_board_skey(db, token=token, user=user, oid=(oid or control))
    session = SessionManager.get(skey)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail="No active session for this board. Call POST /api/v1/session/init first.",
        )
    return session
