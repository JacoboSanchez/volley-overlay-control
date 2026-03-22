import logging
from fastapi import Header, Query, HTTPException
from app.authentication import PasswordAuthenticator
from app.api.session_manager import SessionManager, GameSession

logger = logging.getLogger("APIDeps")


async def verify_api_key(authorization: str = Header(None)):
    """Validate the Bearer token when user authentication is enabled.

    If ``SCOREBOARD_USERS`` is not configured the check is skipped so
    that the API remains open — matching the NiceGUI frontend behaviour.
    """
    if not PasswordAuthenticator.do_authenticate_users():
        return  # no auth required

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing API key. Use 'Authorization: Bearer <key>'.")

    token = authorization.removeprefix("Bearer ").strip()
    if not PasswordAuthenticator.check_api_key(token):
        raise HTTPException(status_code=403, detail="Invalid API key.")


async def get_session(oid: str = Query(..., description="Overlay ID")) -> GameSession:
    """Retrieve a previously initialised ``GameSession``.

    Returns HTTP 404 if no session exists for the given OID — callers
    should call ``POST /api/v1/session/init`` first.
    """
    session = SessionManager.get(oid)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail=f"No active session for OID '{oid}'. Call POST /api/v1/session/init first.",
        )
    return session
