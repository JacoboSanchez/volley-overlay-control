"""Shared admin-token helpers.

Both the match-report routes (``app.match_report``) and the custom-overlay
admin routes (``app.admin.routes``) gate access behind the same admin
credential. Centralising the lookup and the Bearer/``?token=`` resolution
keeps the auth ladder (503 → 401 → 403) consistent across both surfaces
while still letting each caller customise the error strings shown to
the operator.

Two env vars provide the credential:

* ``OVERLAY_MANAGER_PASSWORD`` — legacy plaintext value.
* ``OVERLAY_MANAGER_PASSWORD_HASH`` — scrypt record produced by
  :mod:`app.password_hash`. Preferred when both are set, since
  storing a hash means the cleartext password never lands on disk.

The signing key for match-report capability URLs
(:mod:`app.match_report_signing`) still uses the plaintext password
when one is configured — operators who migrate to the hashed form
pin the key to the hash bytes instead, which keeps the same
"rotating the credential invalidates outstanding URLs" property.
"""

from __future__ import annotations

from fastapi import HTTPException

from app.env_vars_manager import EnvVarsManager
from app.password_hash import verify_password

_DEFAULT_MISSING_TOKEN_DETAIL = (  # nosec B105
    "Authentication required. Pass Authorization: Bearer "
    "<token> or ?token=<token> matching OVERLAY_MANAGER_PASSWORD."
)
_DEFAULT_INVALID_TOKEN_DETAIL = "Invalid token."  # nosec B105

# RFC 7235 §4.1: every 401 response MUST carry a WWW-Authenticate
# header. The realm hint helps the OpenAPI UI label the credential
# prompt and lets operators tell at a glance which ladder rejected
# them when grepping access logs.
_ADMIN_WWW_AUTH = {"WWW-Authenticate": 'Bearer realm="admin"'}


def _stripped_env(key: str) -> str | None:
    raw = EnvVarsManager.get_env_var(key, None)
    if raw is None:
        return None
    raw = str(raw).strip()
    return raw or None


def get_hashed_or_plaintext_env(hash_var: str, plain_var: str) -> str | None:
    """Return the env credential, preferring *hash_var* over *plain_var*.

    Both env vars are read, stripped, and treated as ``None`` when
    empty. The hash form wins so operators migrating to hashed
    credentials do not need to delete the legacy plaintext value.
    """
    return _stripped_env(hash_var) or _stripped_env(plain_var)


def extract_bearer_token(
    authorization: str | None,
    query_token: str | None = None,
) -> str | None:
    """Return the token from ``Authorization: Bearer <token>``.

    Falls back to *query_token* (typically a ``?token=`` query param)
    when the header is absent. Returns ``None`` when neither carries
    a non-empty token.
    """
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        if token:
            return token
    if query_token:
        token = query_token.strip()
        if token:
            return token
    return None


def get_admin_credential() -> str | None:
    """Return the configured admin credential, hash-preferred.

    Returns ``OVERLAY_MANAGER_PASSWORD_HASH`` when set (the verifier
    in :mod:`app.password_hash` recognises and consumes it), else the
    legacy plaintext ``OVERLAY_MANAGER_PASSWORD``. ``None`` when
    neither is set so callers can render a 503.
    """
    return get_hashed_or_plaintext_env(
        "OVERLAY_MANAGER_PASSWORD_HASH",
        "OVERLAY_MANAGER_PASSWORD",
    )


def get_admin_password() -> str | None:
    """Return the legacy plaintext admin password, or ``None``.

    Kept for the match-report signing flow, which uses the password
    bytes (or the hash bytes when only the hash is configured) as
    the HMAC key. Most callers should use :func:`get_admin_credential`
    instead, since that wraps both forms in a verifier-friendly value.
    """
    raw = EnvVarsManager.get_env_var("OVERLAY_MANAGER_PASSWORD", None)
    if raw is None:
        # When only the hash is configured we still need a stable
        # signing key for capability URLs, so use the hash bytes.
        # Rotating the hash still invalidates outstanding signatures.
        h = EnvVarsManager.get_env_var("OVERLAY_MANAGER_PASSWORD_HASH", None)
        if h is None:
            return None
        h = str(h).strip()
        return h or None
    raw = str(raw).strip()
    return raw or None


def require_admin_token(
    authorization: str | None,
    token: str | None = None,
    *,
    missing_password_detail: str,
    missing_token_detail: str = _DEFAULT_MISSING_TOKEN_DETAIL,
    invalid_token_detail: str = _DEFAULT_INVALID_TOKEN_DETAIL,
) -> None:
    """Raise unless the caller presents the admin token.

    Resolves the bearer token from ``Authorization: Bearer <token>``
    first, then from the ``token`` query parameter (when supplied).
    Raises:

    * ``503`` with *missing_password_detail* — neither
      ``OVERLAY_MANAGER_PASSWORD`` nor
      ``OVERLAY_MANAGER_PASSWORD_HASH`` is set.
    * ``401`` with *missing_token_detail* — no credential provided.
    * ``403`` with *invalid_token_detail* — credential doesn't match.

    When the configured credential is a hash, verification goes
    through :func:`app.password_hash.verify_password`, which accepts
    both hash records and plaintext (constant-time in either branch).
    """
    expected = get_admin_credential()
    if expected is None:
        raise HTTPException(status_code=503, detail=missing_password_detail)
    provided = extract_bearer_token(authorization, token)
    if provided is None:
        raise HTTPException(
            status_code=401,
            detail=missing_token_detail,
            headers=_ADMIN_WWW_AUTH,
        )
    if not verify_password(provided, expected):
        raise HTTPException(status_code=403, detail=invalid_token_detail)
