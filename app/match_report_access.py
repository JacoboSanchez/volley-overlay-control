"""Access-control helpers for the match-report routes.

Split out of :mod:`app.match_report`; see that module's docstring for
the full authentication model (public read, signed capability URLs,
admin Bearer / ``?token=`` and the deliberate read/delete separation).
"""

from __future__ import annotations

from app.auth_utils import require_admin_token as _require_admin_token
from app.env_vars_manager import EnvVarsManager


def _public_mode_enabled() -> bool:
    return EnvVarsManager.get_bool_env("MATCH_REPORT_PUBLIC")


def _public_delete_enabled() -> bool:
    """``True`` when the operator has opted into unauthenticated delete.

    Independent from :func:`_public_mode_enabled` on purpose: granting
    public read shouldn't silently authorise public destruction.
    """
    return EnvVarsManager.get_bool_env("MATCH_REPORT_PUBLIC_DELETE")


def _check_access(
    authorization: str | None,
    token: str | None,
    *,
    match_id: str | None = None,
    exp: str | None = None,
    sig: str | None = None,
) -> None:
    """Raise an ``HTTPException`` unless the caller is allowed to read.

    Order of precedence:
      1. ``MATCH_REPORT_PUBLIC=true`` — open access (matches the
         existing ``/overlay/{output_key}`` model);
      2. a valid HMAC signature on ``(match_id, exp)`` (capability URL
         minted by the admin endpoint, no password in the link);
      3. otherwise, ``OVERLAY_MANAGER_PASSWORD`` must be set and
         provided via Bearer header or ``?token=`` query (legacy);
      4. when neither password nor signature works and no public-read
         mode is enabled, return 503 to make misconfiguration loud
         rather than silently public.
    """
    if _public_mode_enabled():
        return
    # Capability URL — no need for the password to be on the wire.
    # Signed URLs are minted by the admin endpoint and embed an
    # ``exp`` that lets the operator share a short-lived link
    # without leaking ``OVERLAY_MANAGER_PASSWORD``.
    if match_id is not None and (exp or sig):
        from app.match_report_signing import verify_signed_query
        if verify_signed_query(match_id, exp, sig):
            return
        # Falling through is intentional: an invalid sig should not
        # leak via a different error than an invalid token, so the
        # require_admin_token call below produces the canonical 401/403.
    _require_admin_token(
        authorization, token,
        # Bandit B106 false positive: this is the error message shown
        # when the password env var is unset, not a hardcoded credential.
        missing_password_detail=(  # nosec B106
            "Match reports are disabled. Set OVERLAY_MANAGER_PASSWORD "
            "for gated access or MATCH_REPORT_PUBLIC=true for open "
            "access."
        ),
    )


def _check_admin_access(authorization: str | None, token: str | None) -> None:
    """Stricter sibling of :func:`_check_access` for destructive actions.

    The public-mode shortcut from :func:`_check_access` deliberately does
    not apply here: ``MATCH_REPORT_PUBLIC=true`` grants read-only access
    (anyone with a non-guessable ``match_id`` can view a report), but
    deletion must still go through the admin token. When
    ``OVERLAY_MANAGER_PASSWORD`` is unset the operator has no way to
    authenticate destructive calls — return 503 rather than silently
    accepting them.
    """
    _require_admin_token(
        authorization, token,
        # Bandit B106 false positive: this is the error message shown
        # when the password env var is unset, not a hardcoded credential.
        missing_password_detail=(  # nosec B106
            "Destructive match-archive actions are disabled. "
            "Set OVERLAY_MANAGER_PASSWORD to enable them."
        ),
    )


