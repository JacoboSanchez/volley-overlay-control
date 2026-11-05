"""Per-session metadata persistence — survives restarts.

The match data (scores, sets, current_set, serve, …) round-trips through
:mod:`app.overlay.state_store` as ``raw_remote_model``. The few flags that
live only on :class:`~app.api.session_manager.GameSession` — simple mode,
custom points/sets limits, rules — are not part of that model, so this
module stores them in the ``runtime_session_meta`` table (see
:mod:`app.db.runtime`) and restores them when the session is re-created.
Older releases kept them in ``data/session_meta_<hash>.json``; those files
are imported once at startup by :mod:`app.db.runtime_import`.

Every call is best-effort: a failed write is logged, never raised, so a
database hiccup cannot wedge a live match.
"""

from __future__ import annotations

import logging
import time

from sqlalchemy import delete

from app.db.runtime import RuntimeSessionMeta, runtime_session
from app.id_validation import API_OID_PATTERN
from app.overlay_key import is_valid_skey

logger = logging.getLogger(__name__)


def is_valid_store_key(oid: object) -> bool:
    """Accept a bare overlay id or a ``<user_id>:<oid>`` storage key.

    The same gate the hashed-filename helper applied, kept so arbitrary
    strings from callers never become runtime rows.
    """
    return isinstance(oid, str) and (
        API_OID_PATTERN.match(oid) is not None or is_valid_skey(oid)
    )


def save_session_meta(oid: str, meta: dict) -> None:
    """Upsert *meta* for *oid*. Best-effort: never raises."""
    if not is_valid_store_key(oid):
        return
    try:
        with runtime_session() as db:
            db.merge(
                RuntimeSessionMeta(
                    store_key=oid, data=dict(meta), updated_at=time.time(),
                )
            )
    except Exception as exc:
        logger.warning("Failed to persist session meta for %r: %s", oid, exc)


def load_session_meta(oid: str) -> dict | None:
    """Read the persisted meta dict for *oid*, or ``None`` if absent."""
    if not is_valid_store_key(oid):
        return None
    try:
        with runtime_session() as db:
            row = db.get(RuntimeSessionMeta, oid)
            data = None if row is None else row.data
    except Exception as exc:
        logger.warning("Failed to read session meta for %r: %s", oid, exc)
        return None
    if not isinstance(data, dict):
        return None
    payload = dict(data)
    payload.pop("_meta", None)
    return payload


def delete_session_meta(oid: str) -> bool:
    """Remove the persisted meta for *oid* if present."""
    if not is_valid_store_key(oid):
        return False
    try:
        with runtime_session() as db:
            result = db.execute(
                delete(RuntimeSessionMeta).where(RuntimeSessionMeta.store_key == oid)
            )
            return bool(getattr(result, "rowcount", 0))
    except Exception as exc:
        logger.warning("Failed to delete session meta for %r: %s", oid, exc)
        return False
