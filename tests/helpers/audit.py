"""Seed the runtime audit table with hand-built records.

Tests that need an audit log with exact, hand-picked ``ts`` values (match
reports, pregame trimming, comeback detection) used to write a JSONL file
straight into the data dir. The log is now rows in ``runtime_audit_events``;
this writes them verbatim, bypassing ``action_log.append``'s monotonic
timestamping, and then invalidates the module's caches exactly as a real
mutation would.
"""

from __future__ import annotations

import json
from collections.abc import Iterable

from sqlalchemy import delete

from app.api import action_log
from app.db.runtime import AuditEvent, runtime_session


def write_audit_records(oid: str, records: Iterable[dict], *, replace: bool = True) -> None:
    """Store *records* as *oid*'s audit log, in order, ``ts`` untouched."""
    rows = list(records)
    with action_log._lock_for(oid):
        with runtime_session() as db:
            if replace:
                db.execute(delete(AuditEvent).where(AuditEvent.store_key == oid))
            for record in rows:
                db.add(
                    AuditEvent(
                        store_key=oid,
                        ts=float(record.get("ts", 0.0) or 0.0),
                        size=len(json.dumps(record, separators=(",", ":")).encode("utf-8")) + 1,
                        record=record,
                    )
                )
        action_log._bytes_per_oid.pop(oid, None)
        action_log._cache_drop_locked(oid)
        action_log._bump_version(oid)
