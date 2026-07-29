"""HMAC-signed capabilities for ``/match/{match_id}/report``.

A report's **owner** mints a per-match URL via
``POST /api/v1/matches/{match_id}/sign-url``; the resulting URL carries
an ``exp`` (expiry) and ``sig`` (HMAC-SHA256) parameter instead of any
credential. Anyone who holds the URL can read the report until ``exp``
passes; no secret ever leaves the server.

The signing key is ``MATCH_REPORT_SECRET`` when set, falling back to
``SESSION_SECRET`` (the same secret that hardens the cookie sessions).

The fallback is the historical behaviour and remains the default, but it
couples two rotations that have nothing to do with each other: rotating
``SESSION_SECRET`` because a session cookie leaked also invalidates every
share link an operator has handed out — and conversely, an operator who
wants to revoke the outstanding report links has no way to do it without
logging every user out. Setting ``MATCH_REPORT_SECRET`` separates them,
so each can be rotated for its own reason. Rotating whichever key is in
use still invalidates every outstanding signed URL, which is the point.

Format
------

* Query parameters: ``?exp=<unix_seconds>&sig=<hex>``.
* Signature payload: ``f"{match_id}|{exp}".encode("utf-8")``.
* Algorithm: HMAC-SHA256, lowercase hex digest.

The verifier checks ``exp`` first (cheap reject for stale links)
and only then computes the HMAC, using ``hmac.compare_digest`` to
avoid a timing oracle.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time

from app.env_vars_manager import EnvVarsManager

logger = logging.getLogger(__name__)


# Cap the TTL the admin endpoint will mint. Operators who want a
# permanent share-link should set ``MATCH_REPORT_PUBLIC=true`` and
# share the bare URL — that's the documented model. The cap stops
# someone from accidentally minting a year-long link in chat.
DEFAULT_TTL_SECONDS = 24 * 60 * 60        # 1 day
MAX_TTL_SECONDS = 30 * 24 * 60 * 60       # 30 days
MIN_TTL_SECONDS = 60                      # 1 minute


def _signing_key() -> bytes | None:
    """Return the HMAC key: ``MATCH_REPORT_SECRET``, else ``SESSION_SECRET``.

    ``SESSION_SECRET`` is minted + persisted on first start (see
    ``app.security_bootstrap.ensure_session_secret``), so signing is
    normally always available. Returns ``None`` only if both are somehow
    unset, in which case the consuming endpoint should 503.

    ``MATCH_REPORT_SECRET`` is not auto-minted: leaving it unset must keep
    validating the links signed before it existed, which it can only do by
    falling through to the same key those links were signed with.
    """
    dedicated = EnvVarsManager.get_env_var("MATCH_REPORT_SECRET", None)
    if dedicated and str(dedicated).strip():
        return str(dedicated).strip().encode("utf-8")
    secret = EnvVarsManager.get_env_var("SESSION_SECRET", None)
    if not secret:
        return None
    return str(secret).encode("utf-8")


def _digest(match_id: str, exp_unix: int) -> str | None:
    key = _signing_key()
    if key is None:
        return None
    msg = f"{match_id}|{exp_unix}".encode()
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def clamp_ttl(ttl_seconds: int | None) -> int:
    """Bound *ttl_seconds* to ``[MIN_TTL_SECONDS, MAX_TTL_SECONDS]``.

    ``None`` and non-positive values fall back to ``DEFAULT_TTL_SECONDS``.
    """
    if ttl_seconds is None:
        return DEFAULT_TTL_SECONDS
    try:
        ttl = int(ttl_seconds)
    except (TypeError, ValueError):
        return DEFAULT_TTL_SECONDS
    if ttl <= 0:
        return DEFAULT_TTL_SECONDS
    return max(MIN_TTL_SECONDS, min(MAX_TTL_SECONDS, ttl))


def make_signed_query(
    match_id: str,
    ttl_seconds: int | None = None,
    *,
    now: float | None = None,
) -> dict | None:
    """Return ``{exp, sig, expires_at}`` for the signed URL, or ``None``.

    ``None`` means signing is unavailable because ``SESSION_SECRET`` is
    unset; callers translate that to a 503.

    *now* is a test seam for deterministic expiry; production callers
    should leave it as ``None``.
    """
    ttl = clamp_ttl(ttl_seconds)
    base_now = time.time() if now is None else float(now)
    exp = int(base_now) + ttl
    sig = _digest(match_id, exp)
    if sig is None:
        return None
    return {"exp": exp, "sig": sig, "expires_at": exp}


def verify_signed_query(
    match_id: str,
    exp: object,
    sig: object,
    *,
    now: float | None = None,
) -> bool:
    """Return ``True`` iff ``(exp, sig)`` is a valid signature for *match_id*.

    Both arguments come from raw query-string parsing so they may be
    ``None`` or arbitrary strings — the function tolerates everything
    and just returns ``False`` on malformed input.
    """
    if not isinstance(sig, str) or not sig:
        return False
    if isinstance(exp, str):
        try:
            exp_int = int(exp)
        except ValueError:
            return False
    elif isinstance(exp, int):
        exp_int = exp
    else:
        return False
    base_now = time.time() if now is None else float(now)
    if exp_int <= int(base_now):
        return False
    expected = _digest(match_id, exp_int)
    if expected is None:
        return False
    return hmac.compare_digest(sig, expected)
