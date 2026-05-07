"""HMAC-signed URLs for ``/match/{match_id}/report``.

The legacy access mechanism for the gated match-report is
``?token=<OVERLAY_MANAGER_PASSWORD>``: the operator pastes the
report URL into a chat tool and the URL contains the actual admin
password. Any browser bookmark, server access log, or HTTP
``Referer`` header that touches that URL leaks the credential.

This module replaces that flow with capability-style signed URLs.
The operator mints a per-match URL via the new admin endpoint
``POST /api/v1/admin/match/{match_id}/sign-url``; the resulting URL
carries an ``exp`` (expiry) and ``sig`` (HMAC-SHA256) parameter
instead of the raw password. Anyone who holds the URL can read the
report until ``exp`` passes; the admin password itself never leaves
the server.

The signing key is derived from ``OVERLAY_MANAGER_PASSWORD`` so the
deployment story stays a single secret. Rotating the admin password
invalidates every outstanding signed URL — that's the desired
behaviour, since a rotation is usually motivated by a compromise.

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

from app.auth_utils import get_admin_password

logger = logging.getLogger(__name__)


# Cap the TTL the admin endpoint will mint. Operators who want a
# permanent share-link should set ``MATCH_REPORT_PUBLIC=true`` and
# share the bare URL — that's the documented model. The cap stops
# someone from accidentally minting a year-long link in chat.
DEFAULT_TTL_SECONDS = 24 * 60 * 60        # 1 day
MAX_TTL_SECONDS = 30 * 24 * 60 * 60       # 30 days
MIN_TTL_SECONDS = 60                      # 1 minute


def _signing_key() -> bytes | None:
    """Return the HMAC key derived from ``OVERLAY_MANAGER_PASSWORD``.

    Returns ``None`` when the password is unset — callers should fall
    back to whatever auth mode is configured (typically a 503 in the
    consuming endpoint).
    """
    pw = get_admin_password()
    if pw is None:
        return None
    return pw.encode("utf-8")


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

    ``None`` means signing is unavailable because the admin password
    is unset; callers translate that to a 503.

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
