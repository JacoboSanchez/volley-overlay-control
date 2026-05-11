"""Compute live match statistics from the per-OID audit log.

The :func:`compute_live_stats` helper here is a thin wrapper around the
post-match :func:`app.match_report._compute_stats` analyzer plus a few
"running" fields (current streak, recent point timeline) that only make
sense while a match is still in progress. Keeping both flavours backed
by the same audit log guarantees the live numbers reconcile with the
final report when the match ends — no second source of truth to drift.
"""

from __future__ import annotations

from typing import Any

from app.api import action_log
from app.match_report import (
    _compute_stats,
    _result_set,
    _running_score_pair,
)


def _current_streak(audit: list[dict[str, Any]]) -> dict[str, Any]:
    """Length of the trailing run of consecutive add_point's by one team.

    A ``set_score`` (manual edit) or a record from a different team
    breaks the streak. Returns ``{"team": None, "n": 0, "set": None}``
    when the latest action wasn't a point or the audit is empty.
    """
    streak_team: int | None = None
    streak_n = 0
    streak_set: int | None = None
    for r in audit:
        if (r.get("params") or {}).get("undo"):
            continue
        action = r.get("action")
        if action == "set_score":
            streak_team, streak_n, streak_set = None, 0, None
            continue
        if action != "add_point":
            continue
        team = (r.get("params") or {}).get("team")
        if team not in (1, 2):
            continue
        set_num = _result_set(r)
        if team == streak_team:
            streak_n += 1
        else:
            streak_team = team
            streak_n = 1
        streak_set = set_num
    if streak_team is None or streak_n == 0:
        return {"team": None, "n": 0, "set": None}
    return {"team": streak_team, "n": streak_n, "set": streak_set}


def _recent_points(
    audit: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    """Return the last *limit* scoring events in chronological order.

    Each entry is a small flat dict suitable for direct broadcast to
    overlay clients::

        {"team": 1, "set": 2, "ts": 1714508400.5,
         "score": [12, 9]}

    ``set_score`` (manual override) events are included because they
    still mutate the visible scoreboard; the overlay tile renders them
    as "edit" chips. Both halves of undo pairs are already filtered by
    :func:`action_log.read_all`.
    """
    if limit <= 0:
        return []
    out: list[dict[str, Any]] = []
    for r in audit:
        if (r.get("params") or {}).get("undo"):
            continue
        action = r.get("action")
        if action not in ("add_point", "set_score"):
            continue
        team = (r.get("params") or {}).get("team")
        if team not in (1, 2):
            continue
        pair = _running_score_pair(r)
        if pair is None:
            continue
        ts = r.get("ts")
        out.append(
            {
                "team": team,
                "set": _result_set(r),
                "ts": float(ts) if isinstance(ts, (int, float)) else None,
                "score": [pair[0], pair[1]],
                "action": action,
            }
        )
    return out[-limit:]


def compute_live_stats(
    oid: str,
    *,
    history_limit: int = 30,
) -> dict[str, Any]:
    """Read the audit log for *oid* and return a live-stats payload.

    The shape mirrors the post-match Highlights block from
    :func:`_compute_stats` (so external consumers can use the same
    renderer) plus three live-only additions:

    * ``current_streak`` — trailing run by one team, mirrors
      ``longest_streak`` but reset to zero whenever a manual edit or
      an opposite-team point breaks it.
    * ``points_history`` — last ``history_limit`` scoring events, each
      with the running score after the action. Driven by the audit
      log, so the rendered trajectory survives operator undos.
    * ``audit_count`` — total non-undo records the stats are computed
      from, useful for cache-busting on the client.
    """
    audit = action_log.read_all(oid)
    base = _compute_stats(audit)
    return {
        "oid": oid,
        "audit_count": sum(
            1 for r in audit if not (r.get("params") or {}).get("undo")
        ),
        "current_streak": _current_streak(audit),
        "longest_streak": base["longest_streak"],
        "set_win_comeback": base["set_win_comeback"],
        "partial_comeback": base["partial_comeback"],
        "longest_rally": base["longest_rally"],
        "total_points": base["total_points"],
        "set_durations": base["set_durations"],
        "points_history": _recent_points(audit, history_limit),
    }
