"""First-admin bootstrap — claim the initial admin with a startup-log token.

Modeled on :func:`app.security_bootstrap.ensure_session_secret`:
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
import threading
from pathlib import Path

from sqlalchemy.orm import Session

from app import security_bootstrap, settings_service
from app.auth import service
from app.db.engine import session_scope
from app.settings_service import set_admin_bootstrap_claimed

logger = logging.getLogger(__name__)

_ADMIN_TOKEN_FILENAME = ".admin_bootstrap_token"  # nosec B105 - filename, not a secret
_TOKEN_BYTES = 32

# Serializes concurrent first-admin claims within this process (the
# deployment model is a single worker). Two simultaneous valid-token
# claims would otherwise both pass the admin_exists() check and create
# two admins.
_claim_lock = threading.Lock()


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
    with _claim_lock:
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
        # Belt-and-braces for multi-process deployments the lock can't
        # cover: if another process claimed while we worked, back out (the
        # route's error path rolls the transaction back).
        if service.admin_exists(db, exclude_user_id=user.id):
            raise GoneError("An administrator already exists.")
        set_admin_bootstrap_claimed(db, True)
        # Secure-by-default: once the instance has its admin, close public
        # sign-ups unless the operator pinned REGISTRATION_OPEN (env var or a
        # prior DB write). The admin can reopen it from the Users page.
        if not settings_service.registration_explicitly_configured(db):
            settings_service.set_registration_open(db, False)
            logger.info(
                "First admin claimed — public registration auto-closed. "
                "Reopen it from the admin Users page or set REGISTRATION_OPEN=true.",
            )
        # Commit while still holding the lock: a concurrent loser then
        # deterministically sees the committed admin (410) instead of racing
        # into the cleared-token 403 path, and its request teardown — which
        # rolls its session back — can never touch rows the winner hasn't
        # made durable yet.
        db.commit()
        clear_bootstrap_token()
        return user


class GoneError(Exception):
    """Raised when the bootstrap window has already closed."""
