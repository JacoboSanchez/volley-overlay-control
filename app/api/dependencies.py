"""Scoreboard API auth + session dependencies.

The control board is reachable three ways:

* **Owner** — a logged-in cookie session (`vsession`). The session is addressed
  by the per-user storage key ``<user_id>:<oid>`` so two users can drive the
  same ``oid`` in isolation.
* **Operator** — an unguessable *control token* passed as ``?c=<token>`` (or the
  ``X-Control-Token`` header). The token resolves to one overlay's storage key,
  granting full board control without a login — the link an owner hands to
  whoever is running the match. It also separates two users sharing an ``oid``.
* **Public bookmark** — ``?u=<username>&oid=<oid>``: a stable, no-login URL the
  owner can bookmark permanently. It is *guessable*, so it only works when the
  overlay has opted into ``public_control``; otherwise it is rejected.

``get_session`` resolves the storage key from whichever credential is present
and is the single authorization gate for board routes — don't add a separate
route-level credential check on a route that already depends on it, or every
action pays a second identical token lookup.
"""

import logging
from dataclasses import dataclass

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
    public_user: str | None,
    user: User | None,
    oid: str | None,
    ensure_owner_overlay: bool = False,
) -> str:
    """Resolve the storage key for the board from whichever credential is present.

    Precedence: control token (operator) → opted-in ``username``+``oid`` (public
    bookmark) → cookie user + ``oid`` (owner).
    """
    if token:
        overlay = overlays_service.get_by_control_token(db, token)
        if overlay is None:
            raise HTTPException(status_code=403, detail=_INVALID_LINK)
        return overlays_service.skey_for(overlay)

    if public_user:
        overlay = overlays_service.get_public_by_username_and_oid(db, public_user, oid or "")
        if overlay is None:
            raise HTTPException(status_code=403, detail=_INVALID_LINK)
        return overlays_service.skey_for(overlay)

    _require_onboarded(user)
    if not oid:
        raise HTTPException(
            status_code=422,
            detail="Missing required query parameter: 'oid' (or alias 'control').",
        )
    if ensure_owner_overlay:
        overlay = overlays_service.get_overlay(db, user.id, oid)  # type: ignore[union-attr]
        if overlay is None:
            overlay = overlays_service.create_overlay(db, user.id, oid)  # type: ignore[union-attr]
        return overlays_service.skey_for(overlay)
    return make_skey(user.id, oid)  # type: ignore[union-attr]  # _require_onboarded ensures non-None


@dataclass(frozen=True)
class BoardAccess:
    """Request-scoped board credentials plus their database session."""

    token: str | None
    public_user: str | None
    user: User | None
    db: Session

    def resolve_skey(
        self,
        oid: str | None,
        *,
        ensure_owner_overlay: bool = False,
    ) -> str:
        return resolve_board_skey(
            self.db,
            token=self.token,
            public_user=self.public_user,
            user=self.user,
            oid=oid,
            ensure_owner_overlay=ensure_owner_overlay,
        )


def board_access(
    token: str | None = Depends(control_token),
    u: str | None = Query(None, description="Username for a public ?u=&oid= board URL"),
    user: User | None = Depends(current_user),
    db: Session = Depends(get_db, scope="function"),
) -> BoardAccess:
    """Collect the shared credential dependency signature in one place."""
    return BoardAccess(token=token, public_user=u, user=user, db=db)


def board_skey(
    oid: str | None = Query(None, description="Overlay ID"),
    control: str | None = Query(None, description="Alias of `oid` for backward compatibility"),
    access: BoardAccess = Depends(board_access),
) -> str:
    """Resolve a board's owner-scoped storage key from request credentials."""
    return access.resolve_skey(oid or control)


def get_session(
    skey: str = Depends(board_skey),
) -> GameSession:
    """Retrieve the board's previously-initialised ``GameSession``.

    The storage key comes from the control token (operator), the opted-in
    ``username``+``oid`` bookmark, or the cookie user + ``oid`` (owner), so a
    caller only ever reaches the board their credential authorizes. Returns 404
    when no session exists (call ``POST /api/v1/session/init`` first).
    Sync ``def`` on purpose — the DB lookup runs in the threadpool.
    """
    session = SessionManager.get(skey)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail="No active session for this board. Call POST /api/v1/session/init first.",
        )
    return session
