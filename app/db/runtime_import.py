"""One-time import of the pre-database runtime files.

Releases before the runtime database kept three kinds of per-overlay file
under ``data/``:

* ``overlay_state_<hash>.json`` — merged overlay render state, with the
  overlay id in ``_meta.overlay_id``;
* ``session_meta_<hash>.json`` — session flags, with the id in
  ``_meta.oid``;
* ``audit_<hash>.jsonl`` plus rotations ``.1`` … ``.N`` (``.N`` oldest) —
  the action audit log, one JSON record per line. The id is only in the
  filename hash, so audit files are matched by hashing the ids recovered
  from the other two kinds of file.

:func:`import_legacy_runtime_files` copies each into its runtime table and
renames the file to ``<name>.imported`` (kept as a backup; never deleted).
It runs on every startup, under the migration lock, and is idempotent and
failure-tolerant:

* a file whose row already exists is only renamed (covers a crash between
  the commit and the rename), so a re-run never duplicates or overwrites;
* each overlay's audit set is inserted in one transaction, so a crash can
  never leave half a log behind, and audit files are matched against every
  key already in the runtime tables, not just this run's;
* a file that cannot be read or stored is logged and left in place for the
  next start — one bad file never blocks startup;
* only per-user storage keys are imported. Files keyed by a bare overlay id
  come from a single-tenant deployment the multi-user app never reads.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any

from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session

from app.api._persistence_paths import DEFAULT_HASH_LEN, data_dir, hashed_filename
from app.db.runtime import (
    AuditEvent,
    OverlayRuntimeState,
    RuntimeSessionMeta,
    get_runtime_engine,
)
from app.overlay_key import is_valid_skey

logger = logging.getLogger(__name__)

IMPORTED_SUFFIX = ".imported"

_HEX = r"[0-9a-f]{" + str(DEFAULT_HASH_LEN) + r"}"
_STATE_RE = re.compile(rf"^overlay_state_{_HEX}\.json$")
_META_RE = re.compile(rf"^session_meta_{_HEX}\.json$")
_AUDIT_RE = re.compile(rf"^audit_{_HEX}\.jsonl(\.[0-9]+)?$")


def _valid_key(value: Any) -> bool:
    """Only per-user storage keys are imported.

    A bare overlay id belongs to a pre-multi-user (single-tenant) deployment,
    whose files the multi-user app deliberately never reads (see README,
    "Upgrading from a single-tenant deployment"); they are left untouched.
    """
    return isinstance(value, str) and is_valid_skey(value)


def _safe_float(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if number == number and number not in (float("inf"), float("-inf")) else 0.0


def _meta_field(meta: Any, field: str) -> Any:
    """Read *field* from a file's ``_meta`` block, tolerating any shape.

    A hand-edited or corrupted file can carry ``_meta`` as a list, string or
    number; that must read as "no key" (file logged and left in place), not
    raise and abort startup.
    """
    return meta.get(field) if isinstance(meta, dict) else None


def _read_json(path: str) -> dict | None:
    try:
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Skipping unreadable legacy file '%s': %s", path, exc)
        return None
    return payload if isinstance(payload, dict) else None


def _mark_imported(path: str) -> None:
    try:
        os.replace(path, path + IMPORTED_SUFFIX)
    except OSError as exc:
        logger.warning("Imported '%s' but could not rename it: %s", path, exc)


def _import_overlay_states(db: Session, directory: str, names: list[str]) -> set[str]:
    keys: set[str] = set()
    for name in names:
        if not _STATE_RE.fullmatch(name):
            continue
        path = os.path.join(directory, name)
        payload = _read_json(path)
        if payload is None:
            continue
        key = _meta_field(payload.get("_meta"), "overlay_id")
        if not isinstance(key, str) or not _valid_key(key):
            logger.warning("Legacy state file '%s' has no per-user _meta.overlay_id; left in place", name)
            continue
        try:
            if db.get(OverlayRuntimeState, key) is None:
                db.add(OverlayRuntimeState(store_key=key, state=payload, updated_at=time.time()))
                db.commit()
        except Exception as exc:
            db.rollback()
            logger.warning("Could not import legacy state file '%s'; left in place: %s", name, exc)
            continue
        _mark_imported(path)
        keys.add(key)
    return keys


def _import_session_metas(db: Session, directory: str, names: list[str]) -> set[str]:
    keys: set[str] = set()
    for name in names:
        if not _META_RE.fullmatch(name):
            continue
        path = os.path.join(directory, name)
        payload = _read_json(path)
        if payload is None:
            continue
        key = _meta_field(payload.pop("_meta", None), "oid")
        if not isinstance(key, str) or not _valid_key(key):
            logger.warning("Legacy session-meta file '%s' has no per-user _meta.oid; left in place", name)
            continue
        try:
            if db.get(RuntimeSessionMeta, key) is None:
                db.add(RuntimeSessionMeta(store_key=key, data=payload, updated_at=time.time()))
                db.commit()
        except Exception as exc:
            db.rollback()
            logger.warning("Could not import legacy session-meta file '%s'; left in place: %s", name, exc)
            continue
        _mark_imported(path)
        keys.add(key)
    return keys


def _audit_paths_oldest_first(directory: str, key: str, names: set[str]) -> list[str]:
    base = hashed_filename("audit_", key, ".jsonl")
    rotated = sorted(
        (
            int(name[len(base) + 1:])
            for name in names
            if name.startswith(base + ".") and name[len(base) + 1:].isdigit()
        ),
        reverse=True,
    )
    paths = [os.path.join(directory, f"{base}.{i}") for i in rotated]
    if base in names:
        paths.append(os.path.join(directory, base))
    return paths


def _read_jsonl(path: str) -> list[tuple[dict, int]]:
    """Parse one audit file, skipping malformed lines.

    An ``OSError`` propagates: a file that cannot be read in full must not
    be imported partially and then renamed as if it had been.
    """
    rows: list[tuple[dict, int]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                rows.append((record, len(stripped.encode("utf-8")) + 1))
    return rows


def _known_keys(db: Session) -> set[str]:
    """Every storage key that already has runtime rows.

    Audit files carry their key only as a filename hash, so they are matched
    against known keys. Including keys imported by an *earlier* run means a
    crash between importing an overlay's state file (and renaming it) and
    importing its audit files does not strand that audit history.
    """
    keys = set(db.scalars(select(OverlayRuntimeState.store_key)))
    keys.update(db.scalars(select(RuntimeSessionMeta.store_key)))
    return {key for key in keys if _valid_key(key)}


def _import_audit_logs(db: Session, directory: str, names: list[str], keys: set[str]) -> int:
    audit_names = {name for name in names if _AUDIT_RE.fullmatch(name)}
    claimed: set[str] = set()
    for key in sorted(keys):
        paths = _audit_paths_oldest_first(directory, key, audit_names)
        if not paths:
            continue
        claimed.update(os.path.basename(p) for p in paths)
        try:
            existing = db.scalar(
                select(func.count()).select_from(AuditEvent).where(AuditEvent.store_key == key)
            )
            if not existing:
                rows = [
                    {
                        "store_key": key,
                        "ts": _safe_float(record.get("ts")),
                        "size": size,
                        "record": record,
                    }
                    for path in paths
                    for record, size in _read_jsonl(path)
                ]
                if rows:
                    db.execute(insert(AuditEvent), rows)
                db.commit()
        except Exception as exc:
            db.rollback()
            logger.warning(
                "Could not import %d legacy audit file(s) for one overlay; left in place: %s",
                len(paths),
                exc,
            )
            continue
        for path in paths:
            _mark_imported(path)
    orphans = audit_names - claimed
    if orphans:
        logger.warning(
            "%d legacy audit file(s) match no known overlay and were left in place",
            len(orphans),
        )
    return len(claimed)


def import_legacy_runtime_files(directory: str | None = None) -> dict[str, int]:
    """Import every legacy runtime file under *directory* (default ``data/``).

    Returns per-kind counts of files handled, for logging and tests.
    """
    directory = directory or data_dir()
    if not os.path.isdir(directory):
        return {"overlay_state": 0, "session_meta": 0, "audit": 0}
    names = sorted(os.listdir(directory))
    with Session(get_runtime_engine()) as db:
        state_keys = _import_overlay_states(db, directory, names)
        meta_keys = _import_session_metas(db, directory, names)
        audit_files = _import_audit_logs(
            db, directory, names, state_keys | meta_keys | _known_keys(db),
        )
    counts = {
        "overlay_state": len(state_keys),
        "session_meta": len(meta_keys),
        "audit": audit_files,
    }
    if any(counts.values()):
        logger.info(
            "Imported legacy runtime files into the runtime database "
            "(overlay states: %d, session metas: %d, audit files: %d); "
            "originals renamed to *%s",
            counts["overlay_state"],
            counts["session_meta"],
            counts["audit"],
            IMPORTED_SUFFIX,
        )
    return counts
