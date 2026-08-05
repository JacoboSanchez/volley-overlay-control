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
from collections.abc import Callable
from collections.abc import Set as AbstractSet

from app.api._persistence_paths import data_dir as _data_dir
from app.api._persistence_paths import overlay_hashed_path
from app.constants import AUDIT_LOG_MAX_BYTES, AUDIT_LOG_MAX_FILES

logger = logging.getLogger(__name__)

# Actions whose forward records can be reversed by an undo (either
# the per-type ``add_X(undo=True)`` flag or the generic
# ``POST /game/undo``). Both code paths now pop from the same audit
# log so the two undo APIs stay consistent.
UNDOABLE_ACTIONS = frozenset({"add_point", "add_set", "add_timeout"})

# Sentinel ``action`` value for pop tombstones. The leading underscore
# guarantees no collision with real ``GameService`` actions.
_POP_TOMBSTONE_ACTION = "_pop"

# Sentinel ``action`` value for restore tombstones — they cancel a
# previously-applied ``_pop`` referencing the same ``ref_ts``. Used by
# the rapid-pair recovery path so an undo that gets reverted within
# the 5 s window leaves no trace in the audit log.
_RESTORE_TOMBSTONE_ACTION = "_restore"

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

# Per-OID monotonic mutation counter. Bumped under ``_lock_for(oid)`` on
# every append / tombstone / clear / delete, so pure read-derived caches
# (notably :mod:`app.api.live_stats`) can detect staleness without
# re-reading and re-parsing the whole JSONL log on every state response.
_version_per_oid: dict[str, int] = {}


# Per-OID cache of parsed records, in append order and *before* tombstone
# filtering — i.e. exactly what ``_read_raw_locked`` would return from disk.
# Stored as ``(version, records)`` and only trusted while the stored version
# still matches ``_version_per_oid``.
#
# Why this exists: every mutation bumps the version, which invalidates the
# live-stats memo in :mod:`app.api.live_stats`, whose recompute calls
# ``read_all``. Since ``GameService.add_point`` audits *before* building its
# state response, that memo was a guaranteed miss on every scored point, and
# each miss re-read and re-parsed the whole log — the active file plus every
# rotated one, up to ``AUDIT_LOG_MAX_BYTES * AUDIT_LOG_MAX_FILES``. Appends
# now fold the record they just wrote into this cache, so the steady-state
# cost of a point is one line appended to a file instead of a full reparse.
#
# Records are cached as the parsed dicts themselves, shared with callers, so
# consumers must treat both the list and its records as read-only.
_raw_cache: dict[str, tuple[int, list[dict]]] = {}


# Optional sink for mutation notifications, installed by
# :func:`app.api.audit_broadcast.install` so live control clients can follow
# the log over the WebSocket they already hold instead of re-GETting
# ``/audit`` after every point. ``None`` (the default) keeps this module
# exactly as it was — nothing in here depends on a listener existing, and
# the test suite runs without one unless it installs its own.
#
# The contract deliberately carries the *version* the mutation produced.
# A listener that receives version N+1 while holding N knows its copy is
# contiguous and can apply the record; any other jump means it missed a
# notification and must re-read. That check is what makes a dropped or
# reordered notification self-healing rather than silently corrupting a
# reader's view.
AuditObserver = Callable[[str, str, int, "dict | None"], None]

_observer: AuditObserver | None = None

# The two events an observer can see. ``append`` carries the record that was
# just written and means "add this to the end". ``invalidate`` carries no
# record and means "re-read from scratch" — used for every mutation that
# changes the meaning of records already written (tombstones, restores,
# clear, delete) or that drops history (rotation).
EVENT_APPEND = "append"
EVENT_INVALIDATE = "invalidate"


def set_observer(observer: AuditObserver | None) -> None:
    """Install (or with ``None``, remove) the mutation observer.

    Process-wide and last-writer-wins: there is exactly one audit log per
    process and exactly one thing that needs to watch it. Tests that install
    an observer are expected to reset it to ``None`` afterwards.
    """
    global _observer
    _observer = observer


def _notify(oid: str, event: str, version: int, record: dict | None = None) -> None:
    """Hand a mutation to the observer, if one is installed.

    Never raises and never blocks the caller on observer failure: an audit
    log that cannot notify is still a correct audit log, and the read path
    (``GET /audit``) remains the source of truth for any client whose live
    feed falls behind. Callers MUST invoke this *outside* ``_lock_for(oid)``
    — the observer performs I/O (a WebSocket fan-out), and holding the
    per-OID write lock across it would let one slow client stall the next
    scored point.
    """
    observer = _observer
    if observer is None:
        return
    try:
        observer(oid, event, version, record)
    except Exception as exc:
        logger.warning("Audit observer failed for %r: %s", oid, exc)


def _bump_version(oid: str) -> None:
    """Increment the OID's mutation counter. Caller holds ``_lock_for(oid)``."""
    _version_per_oid[oid] = _version_per_oid.get(oid, 0) + 1


def _cache_drop_locked(oid: str) -> None:
    """Forget the OID's parsed-record cache. Caller holds ``_lock_for(oid)``."""
    _raw_cache.pop(oid, None)


def _commit_append_locked(oid: str, record: dict) -> None:
    """Bump the version and fold *record* into the parsed-record cache.

    Caller holds ``_lock_for(oid)`` and has just appended *record* to the
    active log file. When the cache is absent or already stale it is simply
    dropped — the next read repopulates it from disk — so this can never
    serve a list that disagrees with the file.
    """
    entry = _raw_cache.get(oid)
    was_fresh = entry is not None and entry[0] == _version_per_oid.get(oid, 0)
    _bump_version(oid)
    if was_fresh and entry is not None:
        entry[1].append(record)
        _raw_cache[oid] = (_version_per_oid[oid], entry[1])
    else:
        _raw_cache.pop(oid, None)


def evict_cache(oid: str) -> None:
    """Release the OID's cached records.

    Called when a session is retired (see
    :meth:`app.api.session_manager.SessionManager.remove`). Without this the
    cache grows for the lifetime of the process, retaining the full parsed
    history of every OID the instance has ever served.

    Only the parsed records are dropped. Two pieces of per-OID bookkeeping
    deliberately survive, because both must stay monotonic for as long as
    the log files exist and both cost a single number per OID:

    * the version counter — a stale reader holding an older version must
      still observe a change;
    * ``_last_ts_per_oid`` — ``_next_ts`` uses it to keep record timestamps
      strictly increasing. The log files outlive the session, so dropping it
      here would let a wall-clock rollback (NTP correction, manual change)
      hand the next append a timestamp at or below the last persisted
      record. Tombstones reference records by ``ts``, so a collision would
      let one ``_pop`` cancel two records — the exact failure ``_next_ts``
      exists to prevent. ``clear``/``delete`` do reset it, correctly: they
      remove the underlying files it is protecting.
    """
    with _lock_for(oid):
        _raw_cache.pop(oid, None)


def version(oid: str) -> int:
    """Return the OID's current mutation counter (``0`` if never written).

    The counter increments on every mutation of the OID's log. If a
    reader observes the same value twice, the log is byte-identical
    between the two observations, so any computation derived purely from
    the log can be cached against this value. The counter lives in
    process memory: it is monotonic for the lifetime of the process and
    deliberately not persisted (a restart re-reads the file anyway).
    """
    return _version_per_oid.get(oid, 0)


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


def _path(oid: str) -> str | None:
    return overlay_hashed_path(_data_dir(), "audit_", oid, ".jsonl")


def _lock_for(oid: str) -> threading.Lock:
    digest = hashlib.sha256(oid.encode("utf-8")).digest()
    idx = int.from_bytes(digest[:4], "big") % _LOCKS_POOL_SIZE
    return _locks_pool[idx]


# ---------------------------------------------------------------------------
# Log rotation
# ---------------------------------------------------------------------------
#
# The active file lives at ``audit_<hash>.jsonl``. When ``append`` finds it
# above ``AUDIT_LOG_MAX_BYTES``, the file is rotated logrotate-style:
# ``.{N-1} -> .N`` (oldest first to avoid clobbering), then active -> .1,
# and anything that would land beyond ``.MAX_FILES-1`` is deleted.
# ``MAX_FILES`` counts the active file plus the rotated set, matching the
# operator's "keep N audit files per OID" mental model.
#
# Rotation runs inside the per-OID lock (same lock that serializes
# appends / pops / clears) so a concurrent reader never sees a torn rename.


def _rotated_path(path: str, index: int) -> str:
    """Return the on-disk path of the *index*-th rotated file (1-based)."""
    return f"{path}.{index}"


def _existing_rotated_indices(path: str) -> list[int]:
    """Return rotated-file indices that exist on disk, ascending order.

    1 is the most recently rotated; higher indices are older. Used by
    ``_iter_log_paths_oldest_first`` to walk the full per-OID log without
    forcing every caller to ``os.path.exists`` the same set of files.
    """
    indices = []
    for i in range(1, AUDIT_LOG_MAX_FILES):
        if os.path.exists(_rotated_path(path, i)):
            indices.append(i)
    return indices


def _iter_log_paths_oldest_first(path: str) -> list[str]:
    """Return [oldest_rotated, ..., active] for the OID at *path*.

    Active appears last so callers (``read_all``) can concatenate
    records in chronological order without a separate sort pass.
    """
    paths: list[str] = []
    # Rotated files: the largest index is the oldest.
    for i in reversed(_existing_rotated_indices(path)):
        paths.append(_rotated_path(path, i))
    if os.path.exists(path):
        paths.append(path)
    return paths


def _rotate_if_needed_locked(path: str) -> bool:
    """Rotate ``path`` when it exceeds ``AUDIT_LOG_MAX_BYTES``.

    Caller must hold ``_lock_for(oid)``. No-op when the file is missing
    or under the threshold, or when ``AUDIT_LOG_MAX_FILES <= 1`` (in
    which case the operator has effectively disabled rotation history
    and we just truncate by deletion on overflow).

    Returns ``True`` when files were moved or removed. Rotation can drop
    the oldest slot, which silently removes records the parsed-record
    cache is still holding, so the caller must invalidate that cache on
    a ``True`` return.
    """
    if AUDIT_LOG_MAX_FILES <= 1:
        # No rotated slots configured — fall back to truncating the
        # active file when it overflows so it cannot grow without bound.
        if os.path.exists(path) and os.path.getsize(path) > AUDIT_LOG_MAX_BYTES:
            try:
                os.remove(path)
            except OSError as exc:
                logger.warning("Failed to truncate oversized audit '%s': %s", path, exc)
                return False
            return True
        return False
    try:
        size = os.path.getsize(path)
    except OSError:
        return False
    if size <= AUDIT_LOG_MAX_BYTES:
        return False
    # Drop the oldest slot if it would exceed the cap after the shift.
    oldest = _rotated_path(path, AUDIT_LOG_MAX_FILES - 1)
    try:
        os.remove(oldest)
    except FileNotFoundError:
        pass
    except OSError as exc:
        logger.warning("Failed to drop oldest rotated audit '%s': %s", oldest, exc)
    # Shift .{i} -> .{i+1} from oldest survivor down so renames never
    # overwrite an existing file (.replace would, but the explicit walk
    # makes the intent obvious in the dominator code path).
    for i in range(AUDIT_LOG_MAX_FILES - 2, 0, -1):
        src = _rotated_path(path, i)
        dst = _rotated_path(path, i + 1)
        if os.path.exists(src):
            try:
                os.replace(src, dst)
            except OSError as exc:
                logger.warning(
                    "Failed to shift rotated audit '%s' -> '%s': %s",
                    src, dst, exc,
                )
                # Files already moved: report rotation so the caller still
                # invalidates its cache.
                return True
    # Active -> .1.
    try:
        os.replace(path, _rotated_path(path, 1))
    except OSError as exc:
        logger.warning("Failed to rotate active audit '%s': %s", path, exc)
    return True


def _append_log_line(
    oid: str, body: dict, error_msg: str, event: str = EVENT_INVALIDATE,
) -> dict | None:
    """Resolve the OID's log path, take the per-OID lock, rotate
    if needed, stamp ``body`` with a fresh monotonic ``ts`` and
    append the resulting record as a single JSON line.

    Returns the written record (with its ``ts``) on success, or
    ``None`` when the OID is invalid or the write fails. The
    public ``append``, ``tombstone_ts`` and ``restore_popped``
    helpers all share this shell — keeping the path / lock /
    rotation / error-handling boilerplate in one place so future
    storage tweaks (e.g. fsync, batched writes) only land here.

    *body* must NOT contain a ``ts`` key — the helper assigns one
    via :func:`_next_ts` so caller-supplied timestamps can't drift
    out of monotonic order. *error_msg* is a ``logger.warning``
    format string accepting two ``%`` parameters: the OID and the
    captured exception.

    *event* is what a live observer is told this write means. It
    defaults to ``EVENT_INVALIDATE`` because two of the three callers
    write tombstones, which change how records already on disk are
    read; only :func:`append` — which genuinely just adds a record to
    the end — passes ``EVENT_APPEND``.
    """
    path = _path(oid)
    if path is None:
        return None
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with _lock_for(oid):
            rotated = _rotate_if_needed_locked(path)
            if rotated:
                # Rotation may have discarded the oldest slot, so the
                # cached records no longer match what is on disk.
                _cache_drop_locked(oid)
            record = {"ts": _next_ts(oid), **body}
            line = json.dumps(
                record, separators=(",", ":"), ensure_ascii=False,
            ) + "\n"
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)
            _commit_append_locked(oid, record)
            new_version = _version_per_oid[oid]
    except Exception as exc:
        logger.warning(error_msg, oid, exc)
        return None
    # Outside the lock: the observer fans out to WebSocket clients, and a
    # slow one must not hold up the next append. Rotation downgrades an
    # append to an invalidate — it can discard the oldest slot, so a reader
    # holding a window that reaches into the dropped file has to re-read
    # rather than extend.
    _notify(
        oid,
        EVENT_INVALIDATE if rotated else event,
        new_version,
        record if event == EVENT_APPEND and not rotated else None,
    )
    return record


def append(oid: str, action: str, params: dict, result: dict) -> dict | None:
    """Atomically append one record. Best-effort: never raises.

    Returns the record that was written (with its assigned ``ts``)
    on success, or ``None`` when the OID is invalid / the write
    fails. Callers that need the assigned ``ts`` for follow-up
    bookkeeping (e.g. the rapid-pair cache) read it from the
    returned dict.
    """
    return _append_log_line(
        oid,
        {"action": action, "params": params, "result": result},
        "Failed to append audit log for %r: %s",
        event=EVENT_APPEND,
    )


def _read_one_file_locked(path: str, oid: str) -> list[dict]:
    """Read every JSON line at *path*, skipping malformed ones."""
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


def _read_raw_locked(path: str, oid: str) -> list[dict]:
    """Read every JSON line in the OID's full log, oldest first.

    Walks ``audit_<hash>.jsonl.{N-1}`` down to ``.1`` and finally the
    active ``audit_<hash>.jsonl`` so chronological order is preserved
    across rotation boundaries. Caller must already hold
    ``_lock_for(oid)``. Tombstone records and the records they
    reference are returned as-is — filtering happens in
    :func:`_apply_tombstones`.

    Served from the parsed-record cache when that cache is current for
    the OID's version, which is the steady state during a live match.
    The returned list is the cached list itself — callers must not
    mutate it (``read_all`` copies before handing it out).
    """
    entry = _raw_cache.get(oid)
    if entry is not None and entry[0] == _version_per_oid.get(oid, 0):
        return entry[1]
    records: list[dict] = []
    for p in _iter_log_paths_oldest_first(path):
        records.extend(_read_one_file_locked(p, oid))
    _raw_cache[oid] = (_version_per_oid.get(oid, 0), records)
    return records


def _apply_tombstones(raw: list[dict]) -> list[dict]:
    """Return *raw* with pop tombstones (and their targets) removed.

    Tombstone records carry ``action == _POP_TOMBSTONE_ACTION`` and
    reference the timestamp of the record they cancel via
    ``ref_ts``. Both the tombstone and the referenced record are
    elided from the returned list.

    Restore tombstones (``_RESTORE_TOMBSTONE_ACTION``) cancel an
    earlier ``_pop`` with the same ``ref_ts`` — used by the rapid-
    pair recovery flow when an undo is reverted within 5 s. The
    forward originally hidden by the ``_pop`` becomes visible
    again. Restores are processed in document order so a later
    ``_pop`` for the same ``ref_ts`` (e.g. a fresh undo of the
    same forward) wins over the prior cancellation.
    """
    tombstoned_ts: set = set()
    has_tombstone = False
    for r in raw:
        action = r.get("action")
        if action == _POP_TOMBSTONE_ACTION:
            has_tombstone = True
            ref_ts = r.get("ref_ts")
            if ref_ts is not None:
                tombstoned_ts.add(ref_ts)
        elif action == _RESTORE_TOMBSTONE_ACTION:
            has_tombstone = True
            ref_ts = r.get("ref_ts")
            if ref_ts is not None:
                tombstoned_ts.discard(ref_ts)
    if not has_tombstone:
        return raw
    return [
        r for r in raw
        if r.get("action") not in (
            _POP_TOMBSTONE_ACTION, _RESTORE_TOMBSTONE_ACTION,
        )
        and r.get("ts") not in tombstoned_ts
    ]


def _has_any_log_file(path: str) -> bool:
    """True when the active file or any rotated file exists for *path*."""
    if os.path.exists(path):
        return True
    return any(
        os.path.exists(_rotated_path(path, i))
        for i in range(1, AUDIT_LOG_MAX_FILES)
    )


def read_all(oid: str) -> list[dict]:
    """Return every record for *oid* in append order. Empty list if absent.

    Walks the active file plus every rotated file so consumers
    (``match_archive``, the ``/audit`` endpoint, the undo path) see
    the full per-OID history regardless of how many rotations have
    occurred since the match started.

    Pop tombstones (and the forward records they cancel) are filtered
    out so callers see the same logical view a full rewrite would
    produce.
    """
    path = _path(oid)
    if path is None or not _has_any_log_file(path):
        return []
    try:
        with _lock_for(oid):
            return _read_visible_locked(path, oid)
    except Exception as exc:
        logger.warning("Failed to read audit log for %r: %s", oid, exc)
        return []


def _read_visible_locked(path: str, oid: str) -> list[dict]:
    """Tombstone-filtered records for *oid*. Caller holds ``_lock_for(oid)``."""
    raw = _read_raw_locked(path, oid)
    filtered = _apply_tombstones(raw)
    # ``_apply_tombstones`` returns ``raw`` itself when there is nothing to
    # filter, and ``raw`` may be the cached list — copy so a caller cannot
    # mutate the cache out from under us. This is a pointer copy, far
    # cheaper than re-reading the log.
    return list(filtered)


def read_page(
    oid: str,
    limit: int,
    before_ts: float | None = None,
) -> tuple[list[dict], float | None, int]:
    """Return up to *limit* records older than *before_ts*, a cursor, and
    the log version the page reflects.

    Cursor-based pagination over the per-OID audit log, walking forward
    from the newest entry and serving fixed-size pages so a long-running
    match (50 K+ records) does not force the operator to ship the whole
    history on every dashboard refresh.

    Parameters:
      * ``limit`` — max number of records to return; clamped to >= 1.
      * ``before_ts`` — when set, only records with ``ts < before_ts``
        are considered. Use ``None`` for the first page (newest
        ``limit`` records).

    Returns ``(records, next_cursor, version)``:
      * ``records`` is in chronological order (oldest first within the
        returned window — same convention as ``read_recent``).
      * ``next_cursor`` is the ``ts`` of the **oldest** returned record
        when more pages remain (caller passes it as ``before_ts`` for
        the next call), or ``None`` when the page is the final one.
      * ``version`` is :func:`version` **as of the same lock hold** that
        produced ``records``.

    That last part is the reason this returns a version at all rather
    than leaving callers to call :func:`version` themselves. Sampling the
    counter outside this lock is wrong in both directions: read it first
    and a mutation landing before the page is built yields a page that
    contains a record the version does not account for — a live client
    would then treat that record's ``audit_append`` push as contiguous
    and append it a second time. Read it after and the page can predate a
    mutation the version already counts, so the client applies the *next*
    push on top of a log it never saw. Under one lock, neither is
    possible.

    Tombstoned records are invisible to the cursor so paging never
    skips past visible records because of an undo that happened
    between calls.
    """
    if limit <= 0:
        return [], None, version(oid)
    path = _path(oid)
    if path is None or not _has_any_log_file(path):
        return [], None, version(oid)
    try:
        with _lock_for(oid):
            records = _read_visible_locked(path, oid)
            log_version = _version_per_oid.get(oid, 0)
    except Exception as exc:
        logger.warning("Failed to read audit page for %r: %s", oid, exc)
        return [], None, version(oid)
    if before_ts is not None:
        records = [r for r in records if r.get("ts", 0) < before_ts]
    page = records[-limit:]
    has_more = len(records) > len(page)
    next_cursor = page[0].get("ts") if (page and has_more) else None
    return page, next_cursor, log_version


def read_recent(oid: str, limit: int = 100) -> list[dict]:
    """Return up to *limit* most-recent records (chronological order)."""
    if limit <= 0:
        return []
    records = read_all(oid)
    return records[-limit:]


def _remove_all_log_files_locked(path: str) -> bool:
    """Delete the active log and every rotated file for *path*.

    Returns True when at least one file was removed. Caller must hold
    the per-OID lock.
    """
    removed = False
    if os.path.exists(path):
        try:
            os.remove(path)
            removed = True
        except OSError as exc:
            logger.warning("Failed to remove active audit '%s': %s", path, exc)
    for i in range(1, AUDIT_LOG_MAX_FILES):
        rp = _rotated_path(path, i)
        if os.path.exists(rp):
            try:
                os.remove(rp)
                removed = True
            except OSError as exc:
                logger.warning("Failed to remove rotated audit '%s': %s", rp, exc)
    return removed


def clear(oid: str) -> None:
    """Truncate the audit log for *oid* if it exists. No-op otherwise.

    Removes both the active file and every rotated file so a match
    reset starts from a genuinely empty log even if rotation happened
    earlier in the same process.
    """
    path = _path(oid)
    if path is None:
        return
    try:
        with _lock_for(oid):
            _remove_all_log_files_locked(path)
            _last_ts_per_oid.pop(oid, None)
            _cache_drop_locked(oid)
            _bump_version(oid)
            new_version = _version_per_oid[oid]
    except Exception as exc:
        logger.warning("Failed to clear audit log for %r: %s", oid, exc)
        return
    # The log is now empty; a reader holding records must drop them.
    _notify(oid, EVENT_INVALIDATE, new_version)


def delete(oid: str) -> bool:
    """Remove every audit file for *oid* (active + rotated).

    Returns True when at least one file existed and was removed.
    """
    path = _path(oid)
    if path is None:
        return False
    try:
        with _lock_for(oid):
            removed = _remove_all_log_files_locked(path)
            _last_ts_per_oid.pop(oid, None)
            _cache_drop_locked(oid)
            _bump_version(oid)
            new_version = _version_per_oid[oid]
    except OSError as exc:
        logger.warning("Failed to delete audit log for %r: %s", oid, exc)
        return False
    _notify(oid, EVENT_INVALIDATE, new_version)
    return removed


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
    if path is None or not _has_any_log_file(path):
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
            # The tombstone always lands on the active file; even when
            # the target lives in a rotated archive the read paths
            # (``read_all`` / ``_apply_tombstones``) walk the whole
            # set together, so a forward record in ``.3`` can be
            # cancelled by a tombstone in the active file.
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)
            _commit_append_locked(oid, tombstone)
            new_version = _version_per_oid[oid]
    except Exception as exc:
        logger.warning("Failed to pop last forward record for %r: %s", oid, exc)
        return None
    # A pop hides a record a reader may already be showing, so this is
    # never an append — the reader has to re-read to see the target
    # disappear. Notified outside the lock like every other mutation.
    _notify(oid, EVENT_INVALIDATE, new_version)
    return target


def tombstone_ts(oid: str, ref_ts: float) -> bool:
    """Append a ``_pop`` tombstone for an arbitrary ``ts``.

    Unlike :func:`pop_last_forward` this does not search for a
    matching forward — it just records "the entry whose ts is
    *ref_ts* is hidden from now on". Used by the rapid-pair flow
    to retroactively hide an undo audit record that was just
    written when the operator immediately reverses the undo.

    Returns ``True`` on success, ``False`` if the OID is invalid
    or the write fails.
    """
    written = _append_log_line(
        oid,
        {"action": _POP_TOMBSTONE_ACTION, "ref_ts": ref_ts},
        "Failed to tombstone ts for %r: %s",
    )
    return written is not None


def restore_popped(oid: str, ref_ts: float) -> bool:
    """Append a ``_restore`` tombstone that cancels a prior ``_pop``.

    The restore re-surfaces a record previously hidden by
    :func:`pop_last_forward` (or :func:`tombstone_ts`) carrying
    the same ``ref_ts``. Used by the rapid-pair recovery flow:
    when the operator un-does an undo within 5 s, the original
    forward that was tombstoned during the undo is revealed
    again so the audit looks like neither the undo nor the
    recovery happened.

    Returns ``True`` on success, ``False`` if the OID is invalid
    or the write fails.
    """
    written = _append_log_line(
        oid,
        {"action": _RESTORE_TOMBSTONE_ACTION, "ref_ts": ref_ts},
        "Failed to restore popped record for %r: %s",
    )
    return written is not None


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
    if path is None or not _has_any_log_file(path):
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
