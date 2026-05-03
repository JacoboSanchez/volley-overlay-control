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

import hashlib
import json
import logging
import os
import re
import tempfile
from typing import Optional

logger = logging.getLogger(__name__)

# Same hash-prefix length used by OverlayStateStore so the on-disk
# convention is uniform.
_FILENAME_HASH_LEN = 20

_OID_PATTERN = re.compile(r"^[A-Za-z0-9._\-]{1,128}$")


def _hashed_basename(oid: str) -> str:
    digest = hashlib.sha256(oid.encode("utf-8")).hexdigest()[:_FILENAME_HASH_LEN]
    return f"session_meta_{digest}.json"


def _data_dir() -> str:
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(base, "..", "..", "data"))


def _state_path(oid: str) -> Optional[str]:
    if not isinstance(oid, str) or _OID_PATTERN.match(oid) is None:
        return None
    return os.path.join(_data_dir(), _hashed_basename(oid))


def save_session_meta(oid: str, meta: dict) -> None:
    """Atomically write *meta* for *oid*. Best-effort: never raises."""
    path = _state_path(oid)
    if path is None:
        return
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        payload = {"_meta": {"oid": oid}, **meta}
        fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f)
            os.replace(tmp_path, path)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except Exception as exc:
        logger.warning("Failed to persist session meta for %r: %s", oid, exc)


def load_session_meta(oid: str) -> Optional[dict]:
    """Read the persisted meta dict for *oid*, or ``None`` if absent."""
    path = _state_path(oid)
    if path is None or not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
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
