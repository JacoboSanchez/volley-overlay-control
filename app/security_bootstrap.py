"""Startup security bootstrap — fail-closed defaults for credentials.

The original posture was "fail-open if unset": ``OVERLAY_SERVER_TOKEN``
and ``SCOREBOARD_USERS`` would both default to "no auth required" with
only a startup log line warning the operator. That is hostile to the
common ``docker compose up`` install where the operator never reads
the warning, and it leaves the seven mutation endpoints on the
overlay router (``POST /api/state/{id}``, ``/create/overlay``,
``/delete/overlay``, ``/api/raw_config``, ``/api/theme``) open to
anyone who can reach the port.

This module flips that default for ``OVERLAY_SERVER_TOKEN`` only —
``SCOREBOARD_USERS`` is left fail-open because it gates user-level
auth and forcing every "Friday-night team" deployment into a mandatory
account model would be a real downgrade. We log loudly when it's
unset instead.

For ``OVERLAY_SERVER_TOKEN``, the resolution order at startup is:

1. ``OVERLAY_SERVER_TOKEN_DISABLED=true`` → keep legacy fail-open.
   Logs a critical warning so the choice is visible in the startup
   tail. Useful for trusted-LAN deployments and local debugging.
2. ``OVERLAY_SERVER_TOKEN=<value>`` already set → honour it.
3. ``data/.overlay_server_token`` exists on disk → load it. This
   keeps the auto-generated token stable across restarts so an
   external ``CustomOverlayBackend`` peer doesn't lose its
   credential every time the container reboots.
4. None of the above → generate ``secrets.token_urlsafe(32)``,
   persist with mode ``0o600`` to the data dir, and inject into
   ``os.environ`` so the rest of the app picks it up via
   ``EnvVarsManager.get_env_var``. Log the path once at INFO so
   operators can capture the value (the log line itself does not
   contain the token).
"""

from __future__ import annotations

import logging
import os
import secrets
import stat
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


_TOKEN_FILENAME = ".overlay_server_token"
_TOKEN_BYTES = 32  # → 43-char URL-safe string

_TRUTHY = ("1", "true", "t", "yes", "on")


def _is_truthy_env(value: Optional[str]) -> bool:
    return isinstance(value, str) and value.strip().lower() in _TRUTHY


def _data_dir() -> str:
    """Return the data directory used by the rest of the app.

    Re-derives the path the same way :func:`app.api.action_log._data_dir`
    does (``<repo>/data``) instead of importing it, because the bootstrap
    runs before the API package is fully wired and we want to avoid
    pulling in optional dependencies just to read a path.
    """
    here = Path(__file__).resolve().parent
    return str(here.parent / "data")


def _token_path() -> Path:
    return Path(_data_dir()) / _TOKEN_FILENAME


def _read_persisted_token(path: Path) -> Optional[str]:
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
        # Write with restrictive perms from the start by opening through
        # ``os.open`` with O_CREAT + O_EXCL + mode 0o600.
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


def ensure_overlay_server_token() -> Optional[str]:
    """Resolve / mint / persist the overlay-server token.

    Returns the active token string, or ``None`` when fail-open mode is
    explicitly enabled or when the operator configured a hashed
    credential (``OVERLAY_SERVER_TOKEN_HASH``) — in the hashed case the
    plaintext lives only on the peer side, never on this server.
    Mutates ``os.environ`` so downstream callers that read via
    :class:`EnvVarsManager` pick the value up transparently.
    """
    if _is_truthy_env(os.environ.get("OVERLAY_SERVER_TOKEN_DISABLED")):
        # Operator opted into the legacy fail-open behaviour. Make the
        # choice loud so it shows up in the startup tail.
        logger.critical(
            "OVERLAY_SERVER_TOKEN_DISABLED=true — overlay server "
            "mutation/config endpoints are UNAUTHENTICATED. Anyone "
            "who can reach this port can mutate overlay state. Set "
            "OVERLAY_SERVER_TOKEN or OVERLAY_SERVER_TOKEN_HASH to "
            "enable authentication."
        )
        return None

    # Hash-only configuration: the operator has set
    # OVERLAY_SERVER_TOKEN_HASH and intentionally not set the
    # plaintext. Auth is enforced (the verifier reads the hash) but
    # we never store cleartext on this server. Skip auto-generation.
    hashed = (os.environ.get("OVERLAY_SERVER_TOKEN_HASH") or "").strip()
    if hashed:
        logger.info(
            "OVERLAY_SERVER_TOKEN_HASH is set — verifying against the "
            "hash; auto-generated plaintext will not be persisted."
        )
        return None

    existing = (os.environ.get("OVERLAY_SERVER_TOKEN") or "").strip()
    if existing:
        return existing

    path = _token_path()
    persisted = _read_persisted_token(path)
    if persisted:
        os.environ["OVERLAY_SERVER_TOKEN"] = persisted
        logger.info(
            "Loaded persisted OVERLAY_SERVER_TOKEN from %s "
            "(set OVERLAY_SERVER_TOKEN env var to override).",
            path,
        )
        return persisted

    new_token = secrets.token_urlsafe(_TOKEN_BYTES)
    persisted_ok = _write_persisted_token(path, new_token)
    os.environ["OVERLAY_SERVER_TOKEN"] = new_token
    if persisted_ok:
        logger.warning(
            "Auto-generated OVERLAY_SERVER_TOKEN and persisted to %s. "
            "External CustomOverlayBackend peers must use the same "
            "value (read it from the file or set OVERLAY_SERVER_TOKEN "
            "explicitly). Set OVERLAY_SERVER_TOKEN_DISABLED=true to "
            "opt out and run unauthenticated.",
            path,
        )
    else:
        logger.warning(
            "Auto-generated OVERLAY_SERVER_TOKEN but could not persist "
            "to disk; the token will rotate on every restart. Set "
            "OVERLAY_SERVER_TOKEN explicitly to fix."
        )
    return new_token


def warn_if_open_scoreboard() -> None:
    """Emit a loud startup warning when the scoreboard API is unauthenticated.

    Unlike :func:`ensure_overlay_server_token`, we do not auto-generate
    user records: ``SCOREBOARD_USERS`` is a JSON map of user→password
    pairs and forcing one onto every fresh install would lock the
    operator out of their own scoreboard. The right posture is "loud
    warning by default, opt-out for trusted LANs".
    """
    raw = (os.environ.get("SCOREBOARD_USERS") or "").strip()
    if raw:
        return
    if _is_truthy_env(os.environ.get("SCOREBOARD_USERS_DISABLED")):
        # Same opt-out shape as the overlay token — operator
        # acknowledged the open posture, no need to warn again.
        return
    logger.warning(
        "SCOREBOARD_USERS is not set — every /api/v1/* scoreboard "
        "endpoint is reachable without authentication. Configure "
        "SCOREBOARD_USERS as a JSON map of {username: {password: ...}} "
        "to require Bearer auth, or set SCOREBOARD_USERS_DISABLED=true "
        "to silence this warning on trusted-LAN deployments."
    )


def run_security_bootstrap() -> None:
    """Entry point invoked from :func:`app.bootstrap.create_app`.

    Centralises the calls so future credential bootstraps (admin
    password rotation, hashed-credential migration) only need a single
    hook. Best-effort: a failure here logs but does not block startup,
    because a missing token is not worse than a broken process.
    """
    try:
        ensure_overlay_server_token()
    except Exception:
        logger.exception("ensure_overlay_server_token failed")
    try:
        warn_if_open_scoreboard()
    except Exception:
        logger.exception("warn_if_open_scoreboard failed")
