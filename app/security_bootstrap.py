"""Startup security bootstrap — auto-mint ``SESSION_SECRET``.

User-level auth is a mandatory cookie-session model (``app.auth``); the
first admin is claimed via a one-time token minted by
``app.auth.bootstrap.ensure_admin_bootstrap``. This module covers the
machine credential ``SESSION_SECRET`` (cookie-session hardening + the HMAC
key for signed match-report URLs).
"""

from __future__ import annotations

import logging
import os
import secrets
import stat
from pathlib import Path

logger = logging.getLogger(__name__)


_SESSION_SECRET_FILENAME = ".session_secret"
_TOKEN_BYTES = 32  # → 43-char URL-safe string

def _data_dir() -> str:
    """Return the data directory used by the rest of the app.

    Re-derives the path the same way :func:`app.api.action_log._data_dir`
    does (``<repo>/data``) instead of importing it, because the bootstrap
    runs before the API package is fully wired and we want to avoid
    pulling in optional dependencies just to read a path.
    """
    here = Path(__file__).resolve().parent
    return str(here.parent / "data")


def _read_persisted_token(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    except OSError as exc:
        logger.warning(
            "Could not read persisted overlay-server token from %s: %s",
            path, exc,
        )
        return None
    return text or None


def _write_persisted_token(path: Path, token: str) -> bool:
    """Atomically write *token* to *path* with ``0o600`` permissions.

    Returns ``True`` on success, ``False`` on any I/O error. Failures
    are logged but never raise — the in-memory token still works for
    this process; we just lose persistence across restart.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write to a temp file first so a crash mid-write cannot leave a
        # truncated token on disk. ``os.replace`` is atomic on POSIX.
        tmp = path.with_suffix(path.suffix + ".tmp")
        # Open with restrictive perms from the start by going through
        # ``os.open(..., O_CREAT | O_TRUNC, 0o600)``. ``O_EXCL`` is
        # deliberately not set: a stale ``.tmp`` from a crashed
        # previous run should be overwritten, not block startup.
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        # Some platforms ignore the mode arg on subsequent opens, so
        # chmod after-the-fact as a belt-and-suspenders.
        fd = os.open(str(tmp), flags, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(token)
        except BaseException:
            try:
                os.unlink(str(tmp))
            except OSError:
                pass
            raise
        try:
            os.chmod(str(tmp), stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
        os.replace(str(tmp), str(path))
    except OSError as exc:
        logger.warning(
            "Could not persist overlay-server token to %s: %s",
            path, exc,
        )
        return False
    return True


def ensure_session_secret() -> str | None:
    """Resolve / mint / persist ``SESSION_SECRET``.

    Used as defense-in-depth for the cookie sessions and as the HMAC key
    for match-report capability URLs. Resolution order:

    1. ``SESSION_SECRET=<value>`` set → honour it.
    2. ``data/.session_secret`` exists → load it (stable across restarts so
       outstanding signed report URLs keep validating).
    3. Otherwise mint ``secrets.token_urlsafe(32)``, persist ``0o600``, and
       inject into ``os.environ``.
    """
    existing = (os.environ.get("SESSION_SECRET") or "").strip()
    if existing:
        return existing

    path = Path(_data_dir()) / _SESSION_SECRET_FILENAME
    persisted = _read_persisted_token(path)
    if persisted:
        os.environ["SESSION_SECRET"] = persisted
        return persisted

    new_secret = secrets.token_urlsafe(_TOKEN_BYTES)
    persisted_ok = _write_persisted_token(path, new_secret)
    os.environ["SESSION_SECRET"] = new_secret
    if persisted_ok:
        logger.info(
            "Auto-generated SESSION_SECRET and persisted to %s. Set "
            "SESSION_SECRET explicitly to pin it across deployments.",
            path,
        )
    else:
        logger.warning(
            "Auto-generated SESSION_SECRET but could not persist it; it will "
            "rotate on every restart (invalidating signed report URLs and "
            "logging every session out). Set SESSION_SECRET explicitly to fix."
        )
    return new_secret


def run_security_bootstrap() -> None:
    """Entry point invoked from :func:`app.bootstrap.create_app`.

    Centralises the calls so future credential bootstraps only need a
    single hook. Best-effort: a failure here logs but does not block
    startup, because a missing token is not worse than a broken process.
    The first-admin bootstrap runs separately in
    :func:`app.auth.bootstrap.ensure_admin_bootstrap` (it needs the DB).
    """
    try:
        ensure_session_secret()
    except Exception:
        logger.exception("ensure_session_secret failed")
