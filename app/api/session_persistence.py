"""Per-session metadata persistence — survives restarts.

For local overlays the match data (scores, sets, current_set, serve, …)
already round-trips through :mod:`app.overlay.state_store` as
``raw_remote_model``. The few flags that live only on
:class:`~app.api.session_manager.GameSession` — simple mode, custom
points/sets limits — are not part of that model, so a process restart
loses them. This module stores those flags in
``data/session_meta_<sha256-prefix>.json`` and restores them when the
session is re-created.

For uno overlays the cloud is the source of truth for match data; the
same metadata file still rehydrates the limits and simple-mode toggle.
"""

import json
import logging
import os

from app.api._persistence_paths import atomic_write_json, hashed_filename
from app.api._persistence_paths import data_dir as _shared_data_dir
from app.api.oid_validation import OID_PATTERN

logger = logging.getLogger(__name__)

_OID_PATTERN = OID_PATTERN


def _data_dir() -> str:
    # Wrapper kept so tests can monkeypatch this attribute.
    return _shared_data_dir()


def _state_path(oid: str) -> str | None:
    from app.overlay_key import is_valid_skey

    if not isinstance(oid, str) or (
        _OID_PATTERN.match(oid) is None and not is_valid_skey(oid)
    ):
        return None
    return os.path.join(_data_dir(), hashed_filename("session_meta_", oid))


def save_session_meta(oid: str, meta: dict) -> None:
    """Atomically write *meta* for *oid*. Best-effort: never raises."""
    path = _state_path(oid)
    if path is None:
        return
    try:
        atomic_write_json(path, {"_meta": {"oid": oid}, **meta})
    except Exception as exc:
        logger.warning("Failed to persist session meta for %r: %s", oid, exc)


def load_session_meta(oid: str) -> dict | None:
    """Read the persisted meta dict for *oid*, or ``None`` if absent."""
    path = _state_path(oid)
    if path is None or not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as exc:
        logger.warning("Failed to read session meta for %r: %s", oid, exc)
        return None
    if not isinstance(payload, dict):
        return None
    payload.pop("_meta", None)
    return payload


def delete_session_meta(oid: str) -> bool:
    """Remove the persisted meta file for *oid* if present."""
    path = _state_path(oid)
    if path is None:
        return False
    try:
        os.remove(path)
        return True
    except FileNotFoundError:
        return False
    except OSError as exc:
        logger.warning("Failed to delete session meta for %r: %s", oid, exc)
        return False
