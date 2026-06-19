"""First-admin bootstrap — claim the initial admin with a startup-log token.

Modeled on :func:`app.security_bootstrap.ensure_overlay_server_token`:
resolve an existing token, else mint + persist one, and log it so the
operator can read it out of ``docker logs`` and claim the first admin
account. Idempotent — once any admin exists the flow is a no-op and the
claim endpoint returns 410.

The token file lives in the same data dir the security bootstrap uses, so
the test ``isolate_security_bootstrap`` fixture redirects it too.
"""

from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path

from sqlalchemy.orm import Session

from app import security_bootstrap
from app.auth import service
from app.db.engine import session_scope
from app.settings_service import set_admin_bootstrap_claimed

logger = logging.getLogger(__name__)

_ADMIN_TOKEN_FILENAME = ".admin_bootstrap_token"  # nosec B105 - filename, not a secret
_TOKEN_BYTES = 32


def _token_path() -> Path:
    return Path(security_bootstrap._data_dir()) / _ADMIN_TOKEN_FILENAME


def get_bootstrap_token() -> str | None:
    """Return the active claim token: ``ADMIN_BOOTSTRAP_TOKEN`` env or file."""
    env = (os.environ.get("ADMIN_BOOTSTRAP_TOKEN") or "").strip()
    if env:
        return env
    return security_bootstrap._read_persisted_token(_token_path())


def clear_bootstrap_token() -> None:
    try:
        _token_path().unlink()
    except FileNotFoundError:
        pass
    except OSError as exc:  # pragma: no cover - best effort
        logger.warning("Could not remove admin bootstrap token file: %s", exc)


def ensure_admin_bootstrap() -> None:
    """Mint/log a one-time admin-claim token when no admin exists yet."""
    try:
        with session_scope() as db:
            if service.admin_exists(db):
                set_admin_bootstrap_claimed(db, True)
                return

            token = get_bootstrap_token()
            minted = False
            if token is None:
                token = secrets.token_urlsafe(_TOKEN_BYTES)
                security_bootstrap._write_persisted_token(_token_path(), token)
                minted = True
    except Exception:  # pragma: no cover - never block startup
        logger.exception("ensure_admin_bootstrap failed")
        return

    source = "auto-generated" if minted else "configured"
    logger.warning(
        "No administrator account exists yet. Claim the first admin by "
        "POSTing the token below to /api/v1/auth/claim-admin (or via the "
        "/claim-admin page):\n"
        "    ADMIN BOOTSTRAP TOKEN (%s): %s",
        source,
        token,
    )


def claim_first_admin(
    db: Session,
    *,
    token: str,
    username: str,
    password: str,
    display_name: str | None = None,
    email: str | None = None,
):
    """Create the first admin if the token matches and no admin exists.

    Returns the created :class:`User`. Raises ``ValueError`` subclasses /
    ``PermissionError`` / ``LookupError`` the caller maps to HTTP codes:

    * ``GoneError``  — an admin already exists (410).
    * ``PermissionError`` — token mismatch / unavailable (403).
    """
    if service.admin_exists(db):
        raise GoneError("An administrator already exists.")
    expected = get_bootstrap_token()
    if not expected or not secrets.compare_digest(token, expected):
        raise PermissionError("Invalid bootstrap token.")

    user = service.create_user(
        db,
        username=username,
        password=password,
        role="admin",
        display_name=display_name,
        email=email,
        must_change_password=False,
    )
    set_admin_bootstrap_claimed(db, True)
    clear_bootstrap_token()
    return user


class GoneError(Exception):
    """Raised when the bootstrap window has already closed."""
