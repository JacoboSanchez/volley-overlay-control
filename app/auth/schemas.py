"""Pydantic request/response models for the auth + account API."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.db.models.user import User


class RegisterRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=8, max_length=256)
    display_name: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=254)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class ClaimAdminRequest(BaseModel):
    token: str = Field(min_length=1, max_length=512)
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=8, max_length=256)
    display_name: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=254)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=8, max_length=256)


class UpdateProfileRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=254)


class UserOut(BaseModel):
    id: int
    username: str
    display_name: str | None
    email: str | None
    role: str
    is_active: bool
    must_change_password: bool

    @classmethod
    def from_user(cls, user: User) -> UserOut:
        return cls(
            id=user.id,
            username=user.username,
            display_name=user.display_name,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            must_change_password=user.must_change_password,
        )


class AuthContext(BaseModel):
    """Public boot payload for the SPA guard — never requires auth."""

    authenticated: bool
    user: UserOut | None = None
    registration_open: bool
    needs_admin_bootstrap: bool


class LoginResponse(BaseModel):
    user: UserOut
    must_change_password: bool


# ---- Admin user-management models -----------------------------------------


class AdminCreateUserRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str | None = Field(default=None, max_length=256)
    display_name: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=254)
    role: str = Field(default="user")


class AdminUpdateUserRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=254)
    role: str | None = None
    is_active: bool | None = None


class TempPasswordResponse(BaseModel):
    user: UserOut
    temp_password: str
