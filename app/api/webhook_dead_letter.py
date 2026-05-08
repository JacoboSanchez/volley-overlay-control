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

logger = logging.getLogger(__name__)

_lock = threading.Lock()

_FILENAME = "webhooks_dead_letter.jsonl"


def _data_dir() -> str:
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(base, "..", "..", "data"))


def _path() -> str:
    return os.path.join(_data_dir(), _FILENAME)


def append(record: dict) -> None:
    """Append a JSON record to the dead-letter file. Best-effort."""
    record = dict(record)
    record.setdefault("ts", time.time())
    path = _path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        line = json.dumps(record, ensure_ascii=False) + "\n"
        with _lock, open(path, "a", encoding="utf-8") as f:
            f.write(line)
    except OSError as exc:
        logger.warning("Failed to append webhook dead-letter: %s", exc)


def read_all() -> list[dict]:
    """Return every record in append order. Empty list when the file is missing."""
    path = _path()
    if not os.path.exists(path):
        return []
    records: list[dict] = []
    try:
        with _lock, open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    logger.debug("Skipping malformed DL line: %s", exc)
    except OSError as exc:
        logger.warning("Failed to read webhook dead-letter: %s", exc)
    return records


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
    except OSError as exc:
        logger.warning("Failed to rewrite webhook dead-letter: %s", exc)


def clear() -> None:
    """Remove the dead-letter file entirely. No-op if missing."""
    path = _path()
    try:
        with _lock:
            if os.path.exists(path):
                os.remove(path)
    except OSError as exc:
        logger.warning("Failed to clear webhook dead-letter: %s", exc)


def filter_since(records: list[dict], since: float | None) -> list[dict]:
    """Return only records whose ``ts`` is >= *since* (or all when None)."""
    if since is None:
        return list(records)
    return [r for r in records if r.get("ts", 0) >= since]
