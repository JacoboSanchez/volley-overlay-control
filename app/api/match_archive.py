"""Match history archive — one DB row per finished match.

When ``GameService`` transitions a session from in-progress to
``match_finished``, the match is archived to the ``match_reports`` table
(was ``data/matches/*.json`` before the multi-user refactor — moved to the
database because the per-user report volume grows).

The public surface is unchanged so callers (the finish hook, the match
routes, and the print report) need no changes:

* ``archive_match(skey, …)`` — insert a row, return the ``match_id``.
* ``list_matches(skey | None)`` — newest-first summaries.
* ``load_match(match_id)`` — full snapshot.
* ``delete_match(match_id)`` / ``delete_for_oid(skey)``.

The ``match_id`` keeps the historical ``match_<sha256(skey)[:20]>_<UTC>``
shape so the HMAC-signed report URLs (:mod:`app.match_report_signing`) and
the ``/match/{id}/report`` route keep working. Every summary/payload reports
``oid`` as the *storage key* (``user_id:oid``) — callers split it back to the
human oid via :mod:`app.overlay_key`.
"""

from __future__ import annotations

import datetime
import logging
import re

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select

from app.api import action_log
from app.api._persistence_paths import DEFAULT_HASH_LEN, hashed_filename
from app.api._persistence_paths import data_dir as _shared_data_dir
from app.db.engine import session_scope
from app.db.models.report import MatchReport
from app.overlay_key import is_valid_skey, make_skey, split_skey

logger = logging.getLogger(__name__)

_FILENAME_HASH_LEN = DEFAULT_HASH_LEN
# ``match_<20-hex>_<UTC-ISO>`` (no ``.json`` now — it is an id, not a file).
_MATCH_ID_RE = re.compile(r"^match_[0-9a-f]{20}_\d{8}T\d{6}_\d{6}Z$")


def _data_dir() -> str:
    # Retained (unused for storage) so the test isolation fixture that
    # monkeypatches ``match_archive._data_dir`` keeps working.
    return _shared_data_dir("matches")


def _skey_hash(skey: str) -> str:
    return hashed_filename("", skey, "")


def _ts_for_now() -> str:
    now = datetime.datetime.now(datetime.UTC)
    return now.strftime("%Y%m%dT%H%M%S") + f"_{now.microsecond:06d}Z"


def _summary(r: MatchReport) -> dict:
    fs = r.final_state or {}
    t1 = fs.get("team_1", {}) or {}
    t2 = fs.get("team_2", {}) or {}
    # Team names live in the captured customization. Resolve them through the
    # same multi-key fallback the printed report uses (``_team_name``:
    # canonical "Team N Name", the legacy "Team N Text Name" alias, snake_case
    # and "nameN") so the list and the report always agree on who played.
    # Reading only "Team N Name" here meant any match whose names were stored
    # under a non-canonical key (e.g. seeded from a preset / predefined team)
    # showed the literal "Team 1" / "Team 2" in the list while the report
    # rendered the real name. ``_team_name`` returns the "Team N" sentinel when
    # truly unnamed; map that back to ``None`` to keep the contract that lets
    # the UI localize the placeholder ("Team 1" / "Equipo 1").
    # Function-local import: ``match_report_render`` imports ``app.api.schemas``
    # at module load, so a top-level import here would create an
    # ``app.api`` <-> ``match_report_render`` cycle that breaks whenever the
    # render module is imported before the ``app.api`` package finishes
    # initializing. By call time both modules are fully loaded.
    from app.match_report_render import _team_name
    cust = r.customization or {}
    name1 = _team_name(cust, 1)
    name2 = _team_name(cust, 2)
    return {
        "match_id": r.match_id,
        "oid": make_skey(r.user_id, r.oid),
        "ended_at": r.ended_at,
        "duration_s": r.duration_s,
        "winning_team": r.winning_team,
        "team_1_sets": t1.get("sets"),
        "team_2_sets": t2.get("sets"),
        "team_1_name": (None if name1 == "Team 1" else name1),
        "team_2_name": (None if name2 == "Team 2" else name2),
        "current_set": fs.get("current_set"),
        # Match mode (indoor / beach / table_tennis) is captured inside the
        # archived ``final_state.config`` (GameStateResponse.config). Surface
        # it so the reports list can filter by match type. ``None`` for
        # matches archived before the mode was recorded.
        "mode": (fs.get("config") or {}).get("mode"),
    }


def _payload(r: MatchReport) -> dict:
    return {
        "match_id": r.match_id,
        "oid": make_skey(r.user_id, r.oid),
        "started_at": r.started_at,
        "ended_at": r.ended_at,
        "duration_s": r.duration_s,
        "winning_team": r.winning_team,
        "final_state": r.final_state or {},
        "customization": r.customization or {},
        "audit_log": r.audit_log or [],
        "config": {
            "points_limit": r.points_limit,
            "points_limit_last_set": r.points_limit_last_set,
            "sets_limit": r.sets_limit,
        },
    }


def archive_match(
    oid: str,
    final_state: dict,
    customization: dict | None = None,
    started_at: float | None = None,
    winning_team: int | None = None,
    points_limit: int | None = None,
    points_limit_last_set: int | None = None,
    sets_limit: int | None = None,
) -> str | None:
    """Insert a snapshot of *oid*'s (a storage key) match. Returns the match_id.

    Returns ``None`` for a non-storage-key (no owning user can be derived)
    or on any DB error — archival never blocks the match-end response.
    """
    skey = oid
    if not is_valid_skey(skey):
        return None
    user_id, raw_oid = split_skey(skey)
    ended_at = datetime.datetime.now(datetime.UTC).timestamp()
    match_id = f"match_{_skey_hash(skey)}_{_ts_for_now()}"
    duration = None if started_at is None else max(0.0, ended_at - float(started_at))
    try:
        with session_scope() as db:
            db.add(MatchReport(
                match_id=match_id,
                user_id=user_id,
                oid=raw_oid,
                started_at=started_at,
                ended_at=ended_at,
                duration_s=duration,
                winning_team=winning_team,
                final_state=final_state or {},
                customization=customization or {},
                audit_log=action_log.read_all(skey),
                points_limit=points_limit,
                points_limit_last_set=points_limit_last_set,
                sets_limit=sets_limit,
            ))
    except Exception as exc:
        logger.warning("Failed to archive match for %r: %s", skey, exc)
        return None
    return match_id


def _scope_predicates(stmt, oid: str | None, user_id: int | None):
    """Apply the skey / user_id scoping shared by list and count.

    Returns the scoped statement, or ``None`` when a provided-but-invalid
    key must match nothing (fail closed).
    """
    if oid and is_valid_skey(oid):
        uid, raw_oid = split_skey(oid)
        return stmt.where(MatchReport.user_id == uid, MatchReport.oid == raw_oid)
    if oid:
        return None
    if user_id is not None:
        return stmt.where(MatchReport.user_id == user_id)
    return stmt


def list_matches(
    oid: str | None = None,
    *,
    user_id: int | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[dict]:
    """Return newest-first match summaries.

    Scope with either a full storage key (*oid* = ``"<user_id>:<oid>"``) for a
    single overlay, or *user_id* for all of one user's matches — both push a
    ``WHERE`` predicate into SQL so a per-user listing never falls back to the
    full-table scan. *limit*/*offset* page the result in SQL; ``limit=None``
    keeps the full listing for internal callers.
    """
    with session_scope() as db:
        stmt = _scope_predicates(select(MatchReport), oid, user_id)
        if stmt is None:
            return []
        stmt = stmt.order_by(MatchReport.ended_at.desc().nullslast())
        if offset:
            stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return [_summary(r) for r in db.execute(stmt).scalars().all()]


def count_matches(oid: str | None = None, *, user_id: int | None = None) -> int:
    """Total matches in the same scope ``list_matches`` would use."""
    with session_scope() as db:
        stmt = _scope_predicates(
            select(func.count()).select_from(MatchReport), oid, user_id,
        )
        if stmt is None:
            return 0
        return int(db.execute(stmt).scalar_one())


def load_match(match_id: str) -> dict | None:
    """Return the full archived snapshot for *match_id*, or ``None``."""
    if not isinstance(match_id, str) or _MATCH_ID_RE.match(match_id) is None:
        return None
    with session_scope() as db:
        row = db.execute(
            select(MatchReport).where(MatchReport.match_id == match_id)
        ).scalar_one_or_none()
        return _payload(row) if row is not None else None


def delete_match(match_id: str) -> bool:
    """Delete the archived match identified by *match_id*."""
    if not isinstance(match_id, str) or _MATCH_ID_RE.match(match_id) is None:
        return False
    with session_scope() as db:
        row = db.execute(
            select(MatchReport).where(MatchReport.match_id == match_id)
        ).scalar_one_or_none()
        if row is None:
            return False
        db.delete(row)
        return True


def delete_for_oid(oid: str) -> int:
    """Delete every archived match for a storage key. Returns the count."""
    if not is_valid_skey(oid):
        return 0
    user_id, raw_oid = split_skey(oid)
    with session_scope() as db:
        result = db.execute(
            sa_delete(MatchReport).where(
                MatchReport.user_id == user_id, MatchReport.oid == raw_oid,
            )
        )
        # Result is typed without rowcount; DML returns a CursorResult that
        # has it.
        return int(getattr(result, "rowcount", 0) or 0)
