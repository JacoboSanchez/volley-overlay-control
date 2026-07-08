"""Admin user management — list/create/update/delete users, reset passwords,
and toggle open registration. All endpoints require an admin session.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app import settings_service, teams_service
from app.auth import service
from app.auth.dependencies import require_admin
from app.auth.schemas import (
    AdminCreateUserRequest,
    AdminUpdateUserRequest,
    TempPasswordResponse,
    UserOut,
)
from app.auth.service import UserError
from app.db.engine import get_db
from app.db.models.user import User

router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])


class RegistrationSetting(BaseModel):
    registration_open: bool


@router.get("/users", response_model=list[UserOut])
def list_users(_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [UserOut.from_user(u) for u in service.list_users(db)]


@router.post("/users", response_model=TempPasswordResponse, status_code=201)
def create_user(
    body: AdminCreateUserRequest,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Create a user. With no password, a temp one is minted and returned;
    the user must change it on first login."""
    # Treat a falsy password (None or "") uniformly: mint a temp password and
    # force a first-login change, so an empty string can't create an account
    # with an unknown random password and no forced-change flag.
    temp = body.password or service.generate_temp_password()
    must_change = not body.password
    try:
        user = service.create_user(
            db, username=body.username, password=temp,
            display_name=body.display_name, email=body.email,
            role=body.role, must_change_password=must_change,
        )
    except UserError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    # Seed the new account with a private "My teams" group holding the full
    # global catalog (one-time; mirrors the 0007 migration for existing users).
    teams_service.seed_user_default_group(db, user.id)
    db.commit()
    return TempPasswordResponse(
        user=UserOut.from_user(user),
        temp_password=temp if must_change else "",
    )


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    body: AdminUpdateUserRequest,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = service.get_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    try:
        if body.display_name is not None or body.email is not None:
            service.update_profile(
                db, user, display_name=body.display_name, email=body.email,
            )
        if body.role is not None:
            service.set_role(db, user, body.role)
        if body.is_active is not None:
            service.set_active(db, user, body.is_active)
    except UserError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    db.commit()
    return UserOut.from_user(user)


@router.post("/users/{user_id}/reset-password", response_model=TempPasswordResponse)
def reset_password(
    user_id: int,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Reset a user to a temporary password (forced change on next login)
    and log out all their existing sessions."""
    from app.auth import sessions

    user = service.get_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    temp = service.reset_to_temp_password(db, user)
    sessions.revoke_all_for_user(db, user.id)
    db.commit()
    return TempPasswordResponse(user=UserOut.from_user(user), temp_password=temp)


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = service.get_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    if service.is_last_active_admin(db, user):
        raise HTTPException(status_code=400, detail="Cannot delete the last administrator.")
    # FK cascade clears the user's DB rows, but the in-process session objects
    # and overlay state files linger until the hourly reaper. Capture the
    # user's overlays (and icon files — their rows cascade, the bytes on disk
    # do not) first, then evict runtime state / unlink files after the delete
    # commits — mirroring ``delete_my_overlay``.
    from app import icons_service, overlays_service
    from app.api.session_manager import SessionManager
    from app.auth import sessions
    from app.overlay import overlay_state_store
    from app.overlay_key import make_skey

    skeys = [make_skey(user.id, o.oid) for o in overlays_service.list_overlays(db, user.id)]
    icon_files = icons_service.filenames_for_user(db, user.id)
    sessions.revoke_all_for_user(db, user.id)
    service.delete_user(db, user)
    db.commit()
    # Match reports key on the user FK, so the cascade above already deleted
    # them — unlike ``delete_my_overlay``, where the owning user survives and
    # the per-overlay archive delete IS required.
    for skey in skeys:
        SessionManager.remove(skey)
        overlay_state_store.delete_overlay(skey)
    icons_service.unlink_files(icon_files)
    return {"ok": True}


@router.get("/registration", response_model=RegistrationSetting)
def get_registration(_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return RegistrationSetting(registration_open=settings_service.registration_open(db))


@router.put("/registration", response_model=RegistrationSetting)
def set_registration(
    body: RegistrationSetting,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    settings_service.set_registration_open(db, body.registration_open)
    db.commit()
    return RegistrationSetting(registration_open=body.registration_open)


@router.post("/webhooks/replay", summary="Re-deliver dead-lettered webhook records")
async def replay_dead_letter_webhooks(
    _admin: User = Depends(require_admin),
    since: float | None = Query(
        None, description="Only replay records whose ts is >= this Unix-seconds value."),
    max_records: int = Query(
        50, ge=1, le=500, description="Cap the records redelivered in this call."),
):
    """Replay a slice of the webhook dead-letter file (oldest first).

    Successful redeliveries are removed; unknown-URL and still-failing records
    are kept. Returns counts only — bodies are never echoed back.
    """
    from app.api import webhook_dead_letter, webhooks

    records = webhook_dead_letter.read_all()
    if since is not None:
        eligible = [r for r in records if r.get("ts", 0) >= since]
        held_back = [r for r in records if r.get("ts", 0) < since]
    else:
        eligible = list(records)
        held_back = []
    replay_set = eligible[:max_records]
    deferred = eligible[max_records:]
    succeeded, still_failing, skipped = await run_in_threadpool(
        webhooks.webhook_dispatcher.replay_records, replay_set,
    )
    new_dl = held_back + deferred + still_failing
    webhook_dead_letter.replace_all(new_dl)
    return {
        "considered": len(replay_set),
        "succeeded": succeeded,
        "still_failing": len(still_failing),
        "skipped_unknown_url": skipped,
        "remaining_in_dl": len(new_dl),
    }
