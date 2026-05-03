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
import tempfile
import threading
import time
from collections.abc import Set as AbstractSet
from typing import Optional

logger = logging.getLogger(__name__)

_OID_PATTERN = re.compile(r"^[A-Za-z0-9._\-]{1,128}$")
_FILENAME_HASH_LEN = 20

# Actions whose forward records can be reversed by an undo (either
# the per-type ``add_X(undo=True)`` flag or the generic
# ``POST /game/undo``). Both code paths now pop from the same audit
# log so the two undo APIs stay consistent.
UNDOABLE_ACTIONS = frozenset({"add_point", "add_set", "add_timeout"})

# Per-OID writers serialize through a fixed-size pool of locks keyed
# by hash(oid). A pool gives bounded memory without the eviction
# race that an LRU dict would create: if an LRU lock were evicted
# while one thread held it, a concurrent caller for the same OID
# would mint a new lock and both would enter the critical section
# (read/append/pop) at once, corrupting the JSONL file. Hash
# collisions across unrelated OIDs just cause negligible spurious
# serialization — the critical sections are short.
_LOCKS_POOL_SIZE = 256
_locks_pool: tuple[threading.Lock, ...] = tuple(
    threading.Lock() for _ in range(_LOCKS_POOL_SIZE)
)


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
    digest = hashlib.sha256(oid.encode("utf-8")).digest()
    idx = int.from_bytes(digest[:4], "big") % _LOCKS_POOL_SIZE
    return _locks_pool[idx]


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
                f.flush()
                os.fsync(f.fileno())
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


def pop_last_forward(
    oid: str,
    allowed_actions: Optional[AbstractSet[str]] = None,
    team: Optional[int] = None,
) -> Optional[dict]:
    """Remove and return the most recent non-undo, allowed record.

    * Undo records (``params.undo`` truthy) are always skipped.
    * If *allowed_actions* is provided, records whose ``action`` is
      not in the set are also skipped — they stay in the log.
    * If *team* is provided, records whose ``params.team`` does not
      match are also skipped. Used by the per-type undo path
      (``add_point(undo=True)`` etc.) to pop only the matching team.
    * The popped entry is NOT re-appended as an undo record; callers
      write a fresh record via :func:`append` after performing the
      inverse mutation.

    Returns ``None`` when no matching forward record exists.
    """
    path = _path(oid)
    if path is None or not os.path.exists(path):
        return None
    try:
        with _lock_for(oid):
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            target_idx = None
            target_record = None
            for idx in range(len(lines) - 1, -1, -1):
                stripped = lines[idx].strip()
                if not stripped:
                    continue
                try:
                    record = json.loads(stripped)
                except json.JSONDecodeError:
                    continue
                params = record.get("params") or {}
                if params.get("undo"):
                    continue
                if (allowed_actions is not None
                        and record.get("action") not in allowed_actions):
                    continue
                if team is not None and params.get("team") != team:
                    continue
                target_idx = idx
                target_record = record
                break
            if target_idx is None:
                return None
            del lines[target_idx]
            # Atomic rewrite: a crash mid-write would otherwise truncate
            # the audit file and lose every preceding record. Use the
            # same mkstemp + os.replace pattern as match_archive.
            dir_name = os.path.dirname(path)
            fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.writelines(lines)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_path, path)
            except BaseException:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
            return target_record
    except Exception as exc:
        logger.warning("Failed to pop last forward record for %r: %s", oid, exc)
        return None


def peek_last_forward(
    oid: str,
    allowed_actions: Optional[AbstractSet[str]] = None,
    team: Optional[int] = None,
) -> Optional[dict]:
    """Return the most recent matching forward record without removing it.

    Same filtering rules as :func:`pop_last_forward`. Used by
    ``GameService.undo_last`` to identify *which* per-type undo to
    dispatch — the dispatched call performs the actual pop.
    """
    path = _path(oid)
    if path is None or not os.path.exists(path):
        return None
    try:
        with _lock_for(oid):
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        for stripped in (line.strip() for line in reversed(lines)):
            if not stripped:
                continue
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            params = record.get("params") or {}
            if params.get("undo"):
                continue
            if (allowed_actions is not None
                    and record.get("action") not in allowed_actions):
                continue
            if team is not None and params.get("team") != team:
                continue
            return record
    except Exception as exc:
        logger.warning("Failed to peek last forward record for %r: %s", oid, exc)
    return None


def count_undoable_forwards(oid: str) -> int:
    """Return the count of pending undoable forward records.

    Forward records that haven't been popped by a subsequent undo
    (per-type or generic) are still in the log; popped ones are
    gone. So this is just "how many undoable forward records exist
    in the log right now".

    Used by ``GameSession`` to maintain a cached ``can_undo`` flag
    without re-reading the file on every state response.
    """
    return sum(
        1 for r in read_all(oid)
        if r.get("action") in UNDOABLE_ACTIONS
        and not (r.get("params") or {}).get("undo")
    )
