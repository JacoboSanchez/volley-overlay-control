"""``/api/v1/auth`` — registration, login/logout, account self-service, and
the first-admin claim endpoint.

Write endpoints share the transactional ``get_db`` dependency.
Cookie set/clear happens on the injected ``Response`` so handlers can still
return a typed Pydantic model.
"""

from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app import teams_service
from app.auth import bootstrap, service, sessions
from app.auth.dependencies import current_user, current_user_or_401, require_user
from app.auth.schemas import (
    AuthContext,
    ChangePasswordRequest,
    ClaimAdminRequest,
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    UpdateProfileRequest,
    UserOut,
)
from app.db.engine import get_db
from app.db.models.user import ROLE_USER, User
from app.settings_service import registration_open

auth_router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])


def _client(request: Request) -> tuple[str | None, str | None]:
    ua = request.headers.get("user-agent")
    ip = request.client.host if request.client else None
    return ua, ip


def _start_session(db: Session, response: Response, request: Request, user: User) -> None:
    ua, ip = _client(request)
    raw = sessions.create_session(db, user, user_agent=ua, ip=ip)
    sessions.set_session_cookie(
        response, raw, secure=sessions.cookie_secure(request.url.scheme),
    )


@auth_router.get("/context", response_model=AuthContext)
def get_context(
    user: User | None = Depends(current_user),
    db: Session = Depends(get_db, scope="function"),
) -> AuthContext:
    """Public boot payload used by the SPA to decide where to route."""
    return AuthContext(
        authenticated=user is not None,
        user=UserOut.from_user(user) if user else None,
        registration_open=registration_open(db),
        needs_admin_bootstrap=not service.admin_exists(db),
    )


@auth_router.get("/me", response_model=UserOut)
def get_me(user: User = Depends(current_user_or_401)) -> UserOut:
    return UserOut.from_user(user)


@auth_router.post("/register", response_model=LoginResponse)
def register(
    body: RegisterRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db, scope="function"),
) -> LoginResponse:
    if not registration_open(db):
        raise HTTPException(status_code=403, detail="Registration is closed.")
    user = service.create_user(
        db,
        username=body.username,
        password=body.password,
        role=ROLE_USER,
        display_name=body.display_name,
        email=body.email,
    )
    # Seed the new account with a private "My teams" group holding the full
    # global catalog (one-time; mirrors the 0007 migration for existing users).
    teams_service.seed_user_default_group(db, user.id)
    _start_session(db, response, request, user)
    return LoginResponse(user=UserOut.from_user(user), must_change_password=False)


@auth_router.post("/login", response_model=LoginResponse)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db, scope="function"),
) -> LoginResponse:
    user = service.authenticate(db, body.username, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    _start_session(db, response, request, user)
    return LoginResponse(
        user=UserOut.from_user(user),
        must_change_password=user.must_change_password,
    )


@auth_router.post("/logout")
def logout(
    response: Response,
    vsession: str | None = Cookie(None),
    db: Session = Depends(get_db, scope="function"),
) -> dict[str, bool]:
    sessions.revoke_session(db, vsession)
    sessions.clear_session_cookie(response)
    return {"ok": True}


@auth_router.post("/change-password", response_model=UserOut)
def change_password(
    body: ChangePasswordRequest,
    user: User = Depends(current_user_or_401),
    vsession: str | None = Cookie(None),
    db: Session = Depends(get_db, scope="function"),
) -> UserOut:
    if not service.verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=403, detail="Current password is incorrect.")
    service.set_password(db, user, body.new_password)
    # Log every other session out; keep this one alive.
    keep = sessions.hash_token(vsession) if vsession else None
    sessions.revoke_all_for_user(db, user.id, except_token_hash=keep)
    return UserOut.from_user(user)


@auth_router.patch("/me", response_model=UserOut)
def update_me(
    body: UpdateProfileRequest,
    user: User = Depends(require_user),
    db: Session = Depends(get_db, scope="function"),
) -> UserOut:
    service.update_profile(
        db, user, display_name=body.display_name, email=body.email,
    )
    return UserOut.from_user(user)


@auth_router.delete("/me")
def delete_me(
    response: Response,
    user: User = Depends(require_user),
    db: Session = Depends(get_db, scope="function"),
) -> dict[str, bool]:
    # Mirror the admin delete guard: a sole administrator self-deleting would
    # lock the instance out of administration entirely.
    if service.is_last_active_admin(db, user):
        raise HTTPException(
            status_code=400,
            detail="Cannot delete the last administrator account.",
        )
    service.delete_user(db, user)
    sessions.clear_session_cookie(response)
    return {"ok": True}


@auth_router.post("/claim-admin", response_model=LoginResponse)
def claim_admin(
    body: ClaimAdminRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db, scope="function"),
) -> LoginResponse:
    try:
        user = bootstrap.claim_first_admin(
            db,
            token=body.token,
            username=body.username,
            password=body.password,
            display_name=body.display_name,
            email=body.email,
        )
    except bootstrap.GoneError as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="Invalid bootstrap token.") from exc
    _start_session(db, response, request, user)
    return LoginResponse(user=UserOut.from_user(user), must_change_password=False)
