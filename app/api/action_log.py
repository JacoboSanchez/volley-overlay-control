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

Pops are tombstone-based: instead of rewriting the whole JSONL file,
``pop_last_forward`` appends a single ``{"action": "_pop",
"ref_ts": <target_ts>}`` sentinel. Read paths
(``read_all`` / ``read_recent`` / ``peek_last_forward``) filter out
tombstones and the records they reference. The file is truncated by
``clear`` at match-end, so tombstone churn does not accumulate
across matches.

All I/O is best-effort: failures are logged but never propagate so a
broken filesystem cannot wedge a live match.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from collections.abc import Set as AbstractSet

from app.api.oid_validation import OID_PATTERN

logger = logging.getLogger(__name__)

_OID_PATTERN = OID_PATTERN
_FILENAME_HASH_LEN = 20

# Actions whose forward records can be reversed by an undo (either
# the per-type ``add_X(undo=True)`` flag or the generic
# ``POST /game/undo``). Both code paths now pop from the same audit
# log so the two undo APIs stay consistent.
UNDOABLE_ACTIONS = frozenset({"add_point", "add_set", "add_timeout"})

# Sentinel ``action`` value for pop tombstones. The leading underscore
# guarantees no collision with real ``GameService`` actions.
_POP_TOMBSTONE_ACTION = "_pop"

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

# Per-OID strictly-monotonic timestamp tracker. Tombstones are
# matched by ``ts``, so two records sharing a timestamp would be
# tombstoned together by a single ``_pop`` — which would silently
# undo more than the operator asked for. ``time.time()`` resolution
# is OS-dependent (~15 ms on Windows) so collisions are possible
# during a flurry of rapid mutations even with the per-OID lock.
# ``_next_ts`` returns ``max(time.time(), _last_ts[oid] + 1e-6)`` so
# successive appends for the same OID always carry strictly
# increasing ``ts`` regardless of OS clock granularity.
_last_ts_per_oid: dict[str, float] = {}
# Float64 holds far more than microsecond precision at unix-epoch
# scale, so a 1 µs minimum step never loses the high-order bits and
# stays human-readable in the audit log.
_TS_MIN_STEP = 1e-6


def _next_ts(oid: str) -> float:
    """Return a per-OID strictly-monotonic timestamp.

    Caller must hold ``_lock_for(oid)``: the dict access is guarded
    by the same lock that serializes file writes for *oid*, so the
    "read last_ts → maybe bump → store" sequence is atomic with the
    enclosing append.
    """
    now = time.time()
    last = _last_ts_per_oid.get(oid)
    if last is not None and now <= last:
        now = last + _TS_MIN_STEP
    _last_ts_per_oid[oid] = now
    return now


def _data_dir() -> str:
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(base, "..", "..", "data"))


def _hashed_basename(oid: str) -> str:
    digest = hashlib.sha256(oid.encode("utf-8")).hexdigest()[:_FILENAME_HASH_LEN]
    return f"audit_{digest}.jsonl"


def _path(oid: str) -> str | None:
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
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with _lock_for(oid):
            record = {
                "ts": _next_ts(oid),
                "action": action,
                "params": params,
                "result": result,
            }
            line = json.dumps(
                record, separators=(",", ":"), ensure_ascii=False,
            ) + "\n"
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)
    except Exception as exc:
        logger.warning("Failed to append audit log for %r: %s", oid, exc)


def _read_raw_locked(path: str, oid: str) -> list[dict]:
    """Read every JSON line at *path*, skipping malformed ones.

    Caller must already hold ``_lock_for(oid)``. Tombstone records and
    the records they reference are returned as-is — filtering happens
    in :func:`_apply_tombstones`.
    """
    records: list[dict] = []
    with open(path, encoding="utf-8") as f:
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
    return records


def _apply_tombstones(raw: list[dict]) -> list[dict]:
    """Return *raw* with pop tombstones (and their targets) removed.

    Tombstone records carry ``action == _POP_TOMBSTONE_ACTION`` and
    reference the timestamp of the forward record they cancel via
    ``ref_ts``. Both the tombstone and the referenced record are
    elided from the returned list.
    """
    tombstoned_ts: set = set()
    has_tombstone = False
    for r in raw:
        if r.get("action") == _POP_TOMBSTONE_ACTION:
            has_tombstone = True
            ref_ts = r.get("ref_ts")
            if ref_ts is not None:
                tombstoned_ts.add(ref_ts)
    if not has_tombstone:
        return raw
    return [
        r for r in raw
        if r.get("action") != _POP_TOMBSTONE_ACTION
        and r.get("ts") not in tombstoned_ts
    ]


def read_all(oid: str) -> list[dict]:
    """Return every record for *oid* in append order. Empty list if absent.

    Pop tombstones (and the forward records they cancel) are filtered
    out so callers see the same logical view a full rewrite would
    produce.
    """
    path = _path(oid)
    if path is None or not os.path.exists(path):
        return []
    try:
        with _lock_for(oid):
            raw = _read_raw_locked(path, oid)
    except Exception as exc:
        logger.warning("Failed to read audit log for %r: %s", oid, exc)
        return []
    return _apply_tombstones(raw)


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
            _last_ts_per_oid.pop(oid, None)
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
            _last_ts_per_oid.pop(oid, None)
        return True
    except FileNotFoundError:
        _last_ts_per_oid.pop(oid, None)
        return False
    except OSError as exc:
        logger.warning("Failed to delete audit log for %r: %s", oid, exc)
        return False


def _find_last_forward(
    records: list[dict],
    allowed_actions: AbstractSet[str] | None = None,
    team: int | None = None,
) -> dict | None:
    """Walk *records* (already tombstone-filtered) in reverse and
    return the most recent non-undo record matching the filters."""
    for record in reversed(records):
        params = record.get("params") or {}
        if params.get("undo"):
            continue
        if (allowed_actions is not None
                and record.get("action") not in allowed_actions):
            continue
        if team is not None and params.get("team") != team:
            continue
        return record
    return None


def pop_last_forward(
    oid: str,
    allowed_actions: AbstractSet[str] | None = None,
    team: int | None = None,
) -> dict | None:
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

    Implementation: appends a single ``_pop`` tombstone record
    referencing the target's ``ts``. ``read_all`` filters tombstones
    out, so the popped record is invisible to subsequent reads.
    Avoids the O(N) full-file rewrite the previous implementation
    performed on every undo.

    Returns ``None`` when no matching forward record exists.
    """
    path = _path(oid)
    if path is None or not os.path.exists(path):
        return None
    try:
        with _lock_for(oid):
            raw = _read_raw_locked(path, oid)
            filtered = _apply_tombstones(raw)
            target = _find_last_forward(filtered, allowed_actions, team)
            if target is None:
                return None
            target_ts = target.get("ts")
            if target_ts is None:
                # Defensive: a record without ``ts`` cannot be
                # tombstoned by reference. Fall back to leaving the
                # log untouched and return ``None`` so callers treat
                # the undo as a no-op rather than losing track of it.
                return None
            tombstone = {
                "ts": _next_ts(oid),
                "action": _POP_TOMBSTONE_ACTION,
                "ref_ts": target_ts,
            }
            line = json.dumps(
                tombstone, separators=(",", ":"), ensure_ascii=False,
            ) + "\n"
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)
            return target
    except Exception as exc:
        logger.warning("Failed to pop last forward record for %r: %s", oid, exc)
        return None


def peek_last_forward(
    oid: str,
    allowed_actions: AbstractSet[str] | None = None,
    team: int | None = None,
) -> dict | None:
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
            raw = _read_raw_locked(path, oid)
    except Exception as exc:
        logger.warning("Failed to peek last forward record for %r: %s", oid, exc)
        return None
    filtered = _apply_tombstones(raw)
    return _find_last_forward(filtered, allowed_actions, team)


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
