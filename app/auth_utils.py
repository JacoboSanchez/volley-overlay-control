"""Shared admin-token helpers.

Both the match-report routes (``app.match_report``) and the custom-overlay
admin routes (``app.admin.routes``) gate access behind the same
``OVERLAY_MANAGER_PASSWORD`` environment variable. Centralising the
password lookup and the Bearer/``?token=`` resolution keeps the auth
ladder (503 → 401 → 403) consistent across both surfaces while still
letting each caller customise the error strings shown to the operator.
"""

from __future__ import annotations

import secrets
from typing import Optional

from fastapi import HTTPException

from app.env_vars_manager import EnvVarsManager

_DEFAULT_MISSING_TOKEN_DETAIL = (  # nosec B105
    "Authentication required. Pass Authorization: Bearer "
    "<token> or ?token=<token> matching OVERLAY_MANAGER_PASSWORD."
)
_DEFAULT_INVALID_TOKEN_DETAIL = "Invalid token."  # nosec B105


def get_admin_password() -> Optional[str]:
    """Return the configured admin password, or ``None`` if unset/empty."""
    raw = EnvVarsManager.get_env_var("OVERLAY_MANAGER_PASSWORD", None)
    if raw is None:
        return None
    raw = str(raw).strip()
    return raw or None


def require_admin_token(
    authorization: Optional[str],
    token: Optional[str] = None,
    *,
    missing_password_detail: str,
    missing_token_detail: str = _DEFAULT_MISSING_TOKEN_DETAIL,
    invalid_token_detail: str = _DEFAULT_INVALID_TOKEN_DETAIL,
) -> None:
    """Raise unless the caller presents the admin token.

    Resolves the bearer token from ``Authorization: Bearer <token>``
    first, then from the ``token`` query parameter (when supplied).
    Raises:

    * ``503`` with *missing_password_detail* — ``OVERLAY_MANAGER_PASSWORD`` unset.
    * ``401`` with *missing_token_detail* — no credential provided.
    * ``403`` with *invalid_token_detail* — credential doesn't match.
    """
    expected = get_admin_password()
    if expected is None:
        raise HTTPException(status_code=503, detail=missing_password_detail)
    provided: Optional[str] = None
    if authorization and authorization.startswith("Bearer "):
        provided = authorization.removeprefix("Bearer ").strip() or None
    if provided is None and token:
        provided = token.strip() or None
    if provided is None:
        raise HTTPException(status_code=401, detail=missing_token_detail)
    if not secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=403, detail=invalid_token_detail)
