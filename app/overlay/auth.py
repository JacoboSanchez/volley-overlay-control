"""Bearer-token gate for the overlay server's mutation endpoints.

Split out of :mod:`app.overlay.routes`; re-exported there so the
documented ``overlay/routes.require_overlay_server_token`` path (see
``AUTHENTICATION.md`` §5) keeps working.
"""

import logging

from fastapi import Header, HTTPException

from app.auth_utils import get_hashed_or_plaintext_env
from app.password_hash import verify_password

logger = logging.getLogger(__name__)


def _get_overlay_server_credential() -> str | None:
    """Return the configured overlay-server credential, hash-preferred.

    ``OVERLAY_SERVER_TOKEN_HASH`` (a scrypt record from
    :mod:`app.password_hash`) wins over the legacy plaintext
    ``OVERLAY_SERVER_TOKEN`` when both are set, so an operator
    migrating to hashed credentials does not have to delete the
    plaintext to switch over. Returns ``None`` when neither is set.
    """
    return get_hashed_or_plaintext_env(
        "OVERLAY_SERVER_TOKEN_HASH",
        "OVERLAY_SERVER_TOKEN",
    )


def require_overlay_server_token(authorization: str = Header(None)) -> None:
    """Gate overlay-server mutation / leaky read endpoints.

    ``OVERLAY_SERVER_TOKEN`` is normally populated at startup by
    :func:`app.security_bootstrap.ensure_overlay_server_token` (auto-
    generated on first run, persisted to ``data/.overlay_server_token``).
    Operators who prefer hash-only configuration can set
    ``OVERLAY_SERVER_TOKEN_HASH`` instead — the bootstrap detects
    that and skips auto-generation.

    When either credential is set the request must include
    ``Authorization: Bearer <token>``; verification goes through
    :func:`app.password_hash.verify_password` which accepts plaintext
    or hash records (constant-time in either branch). The dependency
    stays a no-op only when the operator explicitly opted into legacy
    fail-open via ``OVERLAY_SERVER_TOKEN_DISABLED=true`` — see
    ``AUTHENTICATION.md`` §5 for the migration notes.
    """
    expected = _get_overlay_server_credential()
    if expected is None:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing overlay server token. Use 'Authorization: Bearer <token>'.",
            # RFC 7235 §4.1: 401 responses must advertise the auth
            # scheme. ``realm="overlay-server"`` distinguishes this
            # ladder from the scoreboard and admin ones in client
            # / proxy logs.
            headers={"WWW-Authenticate": 'Bearer realm="overlay-server"'},
        )
    provided = authorization.removeprefix("Bearer ").strip()
    if not verify_password(provided, expected):
        raise HTTPException(status_code=403, detail="Invalid overlay server token.")
