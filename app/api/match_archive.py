"""Match history archive — snapshot per finished match.

When ``GameService.add_point`` or ``GameService.add_set`` transitions a
session from in-progress to ``match_finished``, the match is archived
to ``data/matches/match_<sha256(oid)[:20]>_<UTC-ISO8601>.json``.

Each snapshot bundles:

* ``oid``, ``started_at``, ``ended_at``, ``duration_s``,
  ``winning_team``
* ``final_state`` — the same shape as the WebSocket ``state_update``
  payload, so a stale frontend can render the result without any
  schema translation.
* ``customization`` — team names, colors, logos, layout — frozen at
  match-end, so cosmetic edits made after the match do not retroactively
  rewrite history.
* ``audit_log`` — every audit record from ``app.api.action_log`` for
  this OID at the moment of archival (the log is then cleared on the
  next ``reset`` call).
* ``points_limit``, ``points_limit_last_set``, ``sets_limit`` so the
  archive is interpretable without consulting the live config.

All I/O is best-effort: a failure during archival is logged but does
not block the match-end response.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
import os
import re
import tempfile
from typing import Optional

from app.api import action_log

logger = logging.getLogger(__name__)

_OID_PATTERN = re.compile(r"^[A-Za-z0-9._\-]{1,128}$")
_FILENAME_HASH_LEN = 20

# Match basename: ``match_<20-hex>_<UTC-ISO>.json`` where the timestamp
# is ``YYYYMMDDTHHMMSS_microseconds_Z``. Microsecond precision avoids
# silent overwrites when two matches archive in the same second.
_MATCH_FILENAME_RE = re.compile(
    r"^match_(?P<oid_hash>[0-9a-f]{20})_(?P<ts>\d{8}T\d{6}_\d{6}Z)\.json$"
)


def _data_dir() -> str:
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(
        os.path.join(base, "..", "..", "data", "matches")
    )


def _oid_hash(oid: str) -> str:
    return hashlib.sha256(oid.encode("utf-8")).hexdigest()[:_FILENAME_HASH_LEN]


def _is_valid_oid(oid: str) -> bool:
    return isinstance(oid, str) and _OID_PATTERN.match(oid) is not None


def _ts_for_now() -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    return now.strftime("%Y%m%dT%H%M%S") + f"_{now.microsecond:06d}Z"


def _path_for(oid: str, ts: str) -> str:
    return os.path.join(_data_dir(), f"match_{_oid_hash(oid)}_{ts}.json")


def archive_match(
    oid: str,
    final_state: dict,
    customization: Optional[dict] = None,
    started_at: Optional[float] = None,
    winning_team: Optional[int] = None,
    points_limit: Optional[int] = None,
    points_limit_last_set: Optional[int] = None,
    sets_limit: Optional[int] = None,
) -> Optional[str]:
    """Write a snapshot of *oid*'s match. Returns the match_id, or ``None``.

    The match_id is the basename without the ``.json`` suffix. Use it
    with :func:`load_match` to read the snapshot back.
    """
    if not _is_valid_oid(oid):
        return None
    ts = _ts_for_now()
    path = _path_for(oid, ts)
    ended_at = datetime.datetime.now(datetime.timezone.utc).timestamp()
    payload = {
        "match_id": os.path.basename(path)[:-len(".json")],
        "oid": oid,
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_s": (
            None if started_at is None else max(0.0, ended_at - float(started_at))
        ),
        "winning_team": winning_team,
        "final_state": final_state,
        "customization": customization or {},
        "audit_log": action_log.read_all(oid),
        "config": {
            "points_limit": points_limit,
            "points_limit_last_set": points_limit_last_set,
            "sets_limit": sets_limit,
        },
    }
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
            os.replace(tmp_path, path)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except Exception as exc:
        logger.warning("Failed to archive match for %r: %s", oid, exc)
        return None
    return payload["match_id"]


def list_matches(oid: Optional[str] = None) -> list[dict]:
    """Return summaries for archived matches, newest first.

    When *oid* is provided, only matches for that OID are returned.
    Each summary contains ``match_id``, ``oid``, ``ended_at``,
    ``duration_s``, ``winning_team``, and the final-state header
    (sets and current_set) — enough to render a list without
    re-reading every full snapshot.
    """
    summaries: list[dict] = []
    if not os.path.isdir(_data_dir()):
        return summaries
    target_hash = _oid_hash(oid) if oid and _is_valid_oid(oid) else None
    for filename in os.listdir(_data_dir()):
        m = _MATCH_FILENAME_RE.match(filename)
        if m is None:
            continue
        if target_hash is not None and m.group("oid_hash") != target_hash:
            continue
        try:
            with open(os.path.join(_data_dir(), filename),
                      "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception as exc:
            logger.warning("Skipping unreadable match file '%s': %s",
                           filename, exc)
            continue
        if not isinstance(payload, dict):
            continue
        final_state = payload.get("final_state", {}) or {}
        team_1 = final_state.get("team_1", {}) or {}
        team_2 = final_state.get("team_2", {}) or {}
        summaries.append({
            "match_id": payload.get("match_id"),
            "oid": payload.get("oid"),
            "ended_at": payload.get("ended_at"),
            "duration_s": payload.get("duration_s"),
            "winning_team": payload.get("winning_team"),
            "team_1_sets": team_1.get("sets"),
            "team_2_sets": team_2.get("sets"),
            "current_set": final_state.get("current_set"),
        })
    summaries.sort(key=lambda s: s.get("ended_at") or 0, reverse=True)
    return summaries


def load_match(match_id: str) -> Optional[dict]:
    """Return the full archived snapshot for *match_id*, or ``None``."""
    if not isinstance(match_id, str):
        return None
    if _MATCH_FILENAME_RE.match(match_id + ".json") is None:
        return None
    path = os.path.join(_data_dir(), match_id + ".json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning("Failed to load match %r: %s", match_id, exc)
        return None


def delete_match(match_id: str) -> bool:
    """Remove the archived snapshot identified by *match_id*.

    Returns ``True`` if a file was removed, ``False`` if the match-id is
    syntactically invalid, the file does not exist, or removal failed.
    Validates the basename against ``_MATCH_FILENAME_RE`` so a caller
    can never escape ``data/matches/`` via path traversal.
    """
    if not isinstance(match_id, str):
        return False
    if _MATCH_FILENAME_RE.match(match_id + ".json") is None:
        return False
    path = os.path.join(_data_dir(), match_id + ".json")
    if not os.path.exists(path):
        return False
    try:
        os.remove(path)
        return True
    except OSError as exc:
        logger.warning("Failed to remove match %r: %s", match_id, exc)
        return False


def delete_for_oid(oid: str) -> int:
    """Remove every archived match for *oid*. Returns count deleted."""
    if not _is_valid_oid(oid):
        return 0
    target_hash = _oid_hash(oid)
    if not os.path.isdir(_data_dir()):
        return 0
    removed = 0
    for filename in os.listdir(_data_dir()):
        m = _MATCH_FILENAME_RE.match(filename)
        if m is None or m.group("oid_hash") != target_hash:
            continue
        try:
            os.remove(os.path.join(_data_dir(), filename))
            removed += 1
        except OSError as exc:
            logger.warning("Failed to remove match file '%s': %s",
                           filename, exc)
    return removed
