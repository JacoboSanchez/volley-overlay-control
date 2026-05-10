"""Dead-letter queue for webhook deliveries that exhausted every retry.

Persists one JSON record per failed delivery to
``data/webhooks_dead_letter.jsonl``. The operator replays it on demand
once the receiving service is healthy again via
``POST /api/v1/admin/webhooks/replay``.

Record schema (one JSON object per line)::

    {"ts": 1714508400.123,
     "url": "https://hooks.example.com/scoreboard",
     "event": "set_end",
     "oid": "abc",
     "body": "{...}",
     "last_error": "HTTP 503",
     "attempts": 4}

The ``body`` is stored as a UTF-8 string (the JSON payload that would
have been sent), so the file is human-inspectable. The HMAC ``secret``
is **not** persisted: replay re-resolves the matching ``WebhookTarget``
from the live config and re-signs with the current secret. That way
rotating ``WEBHOOKS_SECRET`` does not strand legacy DL entries with
stale signatures, and a leaked DL file does not leak signing keys.

I/O is protected by a module-level lock so a producer thread (the
webhook ThreadPoolExecutor) and a consumer (the admin replay
handler) cannot interleave half-written records.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import time

from app.api._persistence_paths import data_dir as _shared_data_dir
from app.constants import WEBHOOK_DEAD_LETTER_MAX_RECORDS
from app.metrics import set_dead_letter_size

logger = logging.getLogger(__name__)

_lock = threading.Lock()

_FILENAME = "webhooks_dead_letter.jsonl"


def _data_dir() -> str:
    # Wrapper kept so tests can monkeypatch this attribute.
    return _shared_data_dir()


def _path() -> str:
    return os.path.join(_data_dir(), _FILENAME)


def _count_lines_locked(path: str) -> int:
    """Return the current record count in *path* (caller holds ``_lock``).

    Counts non-empty lines so partially-written tails (the writer crashed
    between ``write`` and ``\n``) are forgiven. Used by ``append`` to
    decide whether to evict and by ``set_dead_letter_size`` callers.
    """
    if not os.path.exists(path):
        return 0
    n = 0
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    n += 1
    except OSError as exc:
        logger.warning("Failed to count webhook DL records: %s", exc)
    return n


def append(record: dict) -> None:
    """Append a JSON record to the dead-letter file.

    When the resulting record count would exceed
    ``WEBHOOK_DEAD_LETTER_MAX_RECORDS``, the oldest entries are dropped
    so the file stays bounded. Eviction is FIFO (preserving the most
    recent failures, which are most likely to still be relevant for a
    replay) and runs under the same lock that serialises every other
    mutation, so a concurrent ``read_all`` or ``replay_records`` can
    never observe a torn rewrite.

    Best-effort: filesystem errors are logged but never raised so a
    write failure here cannot kill the GameService action that fired
    the webhook.
    """
    record = dict(record)
    record.setdefault("ts", time.time())
    path = _path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with _lock:
            current = _count_lines_locked(path)
            cap = max(1, WEBHOOK_DEAD_LETTER_MAX_RECORDS)
            if current + 1 > cap:
                # Need to drop ``overflow`` of the oldest records to make
                # room for the new one. Read everything, slice the tail,
                # and rewrite atomically (tempfile + os.replace).
                overflow = current + 1 - cap
                kept = _read_records_locked(path)[overflow:]
                kept.append(record)
                _write_records_atomic_locked(path, kept)
                logger.warning(
                    "Webhook DL evicted %d oldest records (cap=%d)",
                    overflow, cap,
                )
                set_dead_letter_size(len(kept))
                return
            line = json.dumps(record, ensure_ascii=False) + "\n"
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)
            set_dead_letter_size(current + 1)
    except OSError as exc:
        logger.warning("Failed to append webhook dead-letter: %s", exc)


def _read_records_locked(path: str) -> list[dict]:
    """Read every JSON record at *path* (caller holds ``_lock``)."""
    records: list[dict] = []
    if not os.path.exists(path):
        return records
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    logger.debug("Skipping malformed DL line: %s", exc)
    except OSError as exc:
        logger.warning("Failed to read webhook DL: %s", exc)
    return records


def _write_records_atomic_locked(path: str, records: list[dict]) -> None:
    """Tempfile + ``os.replace`` rewrite (caller holds ``_lock``)."""
    fd, tmp_path = tempfile.mkstemp(
        dir=os.path.dirname(path), suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def read_all() -> list[dict]:
    """Return every record in append order. Empty list when the file is missing."""
    path = _path()
    with _lock:
        return _read_records_locked(path)


def count() -> int:
    """Return the current record count without parsing every line."""
    path = _path()
    with _lock:
        return _count_lines_locked(path)


def replace_all(records: list[dict]) -> None:
    """Atomically rewrite the dead-letter to contain only *records*.

    Tempfile + ``os.replace`` so a crash mid-write cannot leave the
    file half-written; either the new content or the old one survives.
    Used by the admin replay handler after pruning successfully
    re-delivered entries.
    """
    path = _path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with _lock:
            _write_records_atomic_locked(path, records)
        set_dead_letter_size(len(records))
    except OSError as exc:
        logger.warning("Failed to rewrite webhook dead-letter: %s", exc)


def clear() -> None:
    """Remove the dead-letter file entirely. No-op if missing."""
    path = _path()
    try:
        with _lock:
            if os.path.exists(path):
                os.remove(path)
        set_dead_letter_size(0)
    except OSError as exc:
        logger.warning("Failed to clear webhook dead-letter: %s", exc)


def filter_since(records: list[dict], since: float | None) -> list[dict]:
    """Return only records whose ``ts`` is >= *since* (or all when None)."""
    if since is None:
        return list(records)
    return [r for r in records if r.get("ts", 0) >= since]
