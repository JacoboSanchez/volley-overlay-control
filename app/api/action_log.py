"""Per-OID action audit log — append-only JSONL.

Every state-mutating call in :mod:`app.api.game_service` writes a single
record to ``data/audit_<sha256[:20]>.jsonl``. Records are JSON one-per-line
to keep appends atomic and parsing trivial::

    {"ts": 1714508400.123,
     "action": "add_point",
     "params": {"team": 1, "undo": false},
     "result": {"current_set": 1,
                "match_finished": false,
                "team_1": {"sets": 0, "score": 5, "timeouts": 0},
                "team_2": {"sets": 0, "score": 3, "timeouts": 0},
                "serve": "A"}}

Used by:

* §1.2 match history archive — the audit log is bundled into the
  per-match snapshot at ``data/matches/{oid}/{ISO8601}.json`` on
  match-end so the entire scoring trajectory is preserved.
* §1.4 server-side undo stack — the new ``POST /api/v1/game/undo``
  endpoint pops the last forward (non-undo) record and reverses it
  via the inverse ``GameService`` call.

All I/O is best-effort: failures are logged but never propagate so a
broken filesystem cannot wedge a live match.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
from collections import defaultdict
from typing import Optional

logger = logging.getLogger(__name__)

_OID_PATTERN = re.compile(r"^[A-Za-z0-9._\-]{1,128}$")
_FILENAME_HASH_LEN = 20

# Per-OID locks coordinate concurrent writers within the same process.
_locks_lock = threading.Lock()
_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)


def _data_dir() -> str:
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(base, "..", "..", "data"))


def _hashed_basename(oid: str) -> str:
    digest = hashlib.sha256(oid.encode("utf-8")).hexdigest()[:_FILENAME_HASH_LEN]
    return f"audit_{digest}.jsonl"


def _path(oid: str) -> Optional[str]:
    if not isinstance(oid, str) or _OID_PATTERN.match(oid) is None:
        return None
    return os.path.join(_data_dir(), _hashed_basename(oid))


def _lock_for(oid: str) -> threading.Lock:
    with _locks_lock:
        return _locks[oid]


def append(oid: str, action: str, params: dict, result: dict) -> None:
    """Atomically append one record. Best-effort: never raises."""
    path = _path(oid)
    if path is None:
        return
    record = {
        "ts": time.time(),
        "action": action,
        "params": params,
        "result": result,
    }
    line = json.dumps(record, separators=(",", ":"), ensure_ascii=False) + "\n"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with _lock_for(oid):
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)
    except Exception as exc:
        logger.warning("Failed to append audit log for %r: %s", oid, exc)


def read_all(oid: str) -> list[dict]:
    """Return every record for *oid* in append order. Empty list if absent."""
    path = _path(oid)
    if path is None or not os.path.exists(path):
        return []
    records: list[dict] = []
    try:
        with _lock_for(oid):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError as exc:
                        logger.debug(
                            "Skipping malformed audit line for %r: %s",
                            oid, exc,
                        )
    except Exception as exc:
        logger.warning("Failed to read audit log for %r: %s", oid, exc)
    return records


def read_recent(oid: str, limit: int = 100) -> list[dict]:
    """Return up to *limit* most-recent records (chronological order)."""
    if limit <= 0:
        return []
    records = read_all(oid)
    return records[-limit:]


def clear(oid: str) -> None:
    """Truncate the audit log for *oid* if it exists. No-op otherwise."""
    path = _path(oid)
    if path is None:
        return
    try:
        with _lock_for(oid):
            if os.path.exists(path):
                os.remove(path)
    except Exception as exc:
        logger.warning("Failed to clear audit log for %r: %s", oid, exc)


def delete(oid: str) -> bool:
    """Remove the audit file. Returns True if a file was removed."""
    path = _path(oid)
    if path is None:
        return False
    try:
        with _lock_for(oid):
            os.remove(path)
        return True
    except FileNotFoundError:
        return False
    except OSError as exc:
        logger.warning("Failed to delete audit log for %r: %s", oid, exc)
        return False


def pop_last_forward(oid: str) -> Optional[dict]:
    """Remove and return the most recent non-undo record, if any.

    Records whose ``params.undo`` is truthy are skipped — they are
    themselves undo entries and shouldn't be re-undone. This is the
    primitive that powers the server-side undo stack (§1.4).

    Note: the popped entry is NOT re-appended as an undo record;
    callers (typically GameService.undo_last) write a fresh record
    via :func:`append` after performing the inverse mutation.
    """
    path = _path(oid)
    if path is None or not os.path.exists(path):
        return None
    try:
        with _lock_for(oid):
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            # Walk backward to find the most recent forward record.
            target_idx = None
            for idx in range(len(lines) - 1, -1, -1):
                stripped = lines[idx].strip()
                if not stripped:
                    continue
                try:
                    record = json.loads(stripped)
                except json.JSONDecodeError:
                    continue
                if record.get("params", {}).get("undo"):
                    continue
                target_idx = idx
                target_record = record
                break
            if target_idx is None:
                return None
            # Rewrite the file without the popped line.
            del lines[target_idx]
            with open(path, "w", encoding="utf-8") as f:
                f.writelines(lines)
            return target_record
    except Exception as exc:
        logger.warning("Failed to pop last forward record for %r: %s", oid, exc)
        return None
