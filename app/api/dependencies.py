import logging
from fastapi import Header, Query, HTTPException, Request
from app.authentication import PasswordAuthenticator
from app.api.session_manager import SessionManager, GameSession

logger = logging.getLogger("APIDeps")

async def verify_api_key(authorization: str = Header(None)):
    """Validate the Bearer token when user authentication is enabled.

    If ``SCOREBOARD_USERS`` is not configured the check is skipped so
    that the API remains open.
    """
    if not PasswordAuthenticator.do_authenticate_users():
        return  # no auth required

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing API key. Use 'Authorization: Bearer <key>'.")

    token = authorization.removeprefix("Bearer ").strip()
    if not PasswordAuthenticator.check_api_key(token):
        raise HTTPException(status_code=403, detail="Invalid API key.")

def get_current_username(authorization: str | None) -> str | None:
    """Return the username for a Bearer token header, or ``None``.

    Does not raise: used by endpoints that want to filter by caller identity
    without requiring authentication (e.g. ``GET /overlays``).
    """
    if not authorization:
        return None
    token = authorization.removeprefix("Bearer ").strip()
    return PasswordAuthenticator.get_username_for_api_key(token)

def check_oid_access(authorization: str, oid: str):
    """Verify that the API key has permission for the requested OID."""
    if not PasswordAuthenticator.do_authenticate_users():
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing API key.")

    username = get_current_username(authorization)
    if not username:
        raise HTTPException(status_code=403, detail="Invalid API key.")
        
    users = PasswordAuthenticator._get_users()
    userconf = users.get(username)
    if userconf:
        allowed_oid = userconf.get("control")
        if allowed_oid and allowed_oid != oid:
            raise HTTPException(status_code=403, detail="Not authorized for this OID.")

async def get_session(
    request: Request,
    oid: str = Query(..., description="Overlay ID")
) -> GameSession:
    """Retrieve a previously initialised ``GameSession``.

    Returns HTTP 404 if no session exists for the given OID — callers
    should call ``POST /api/v1/session/init`` first.
    """
    authorization = request.headers.get("authorization", "")
    check_oid_access(authorization, oid)

    session = SessionManager.get(oid)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail=f"No active session for OID '{oid}'. Call POST /api/v1/session/init first.",
        )
    return session
