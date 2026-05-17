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


def _is_undo_record(record: dict[str, Any]) -> bool:
    """``True`` for audit records that reverse an earlier action.

    The modern unified-undo path tombstones the original forward in
    the audit file; :func:`action_log._apply_tombstones` (called from
    :func:`action_log.read_all`) drops the forward but the *undo*
    record itself — ``params.undo == True`` — survives. Legacy audit
    snapshots from pre-unification deployments can additionally carry
    both halves of the pair, where the forward isn't tombstoned at
    all.

    Either way, every aggregator in this module wants the same
    visible-history semantic as :func:`app.match_report._collapse_undos`:
    skip undo records so the stats reflect "what actually counted".
    Centralising the predicate here is the single source of truth for
    that filter — match the existing helper rather than re-implementing
    the dict-lookup at each call site.
    """
    return bool((record.get("params") or {}).get("undo"))


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
        if _is_undo_record(r):
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


def _scoring_events(audit: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Walk the audit once and return all scoring events as flat dicts.

    Each entry has::

        {"team": 1, "set": 2, "ts": 1714508400.5,
         "score": [12, 9], "action": "add_point"}

    ``set_score`` (manual override) events are included because they
    still mutate the visible scoreboard; consumers can render them
    differently (chip-style "edit" markers). Undo records are filtered
    via :func:`_is_undo_record` — see its docstring for why the filter
    is still required even after :func:`action_log.read_all`.
    """
    out: list[dict[str, Any]] = []
    for r in audit:
        if _is_undo_record(r):
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
    return out


def _recent_points(
    events: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    """Return the last *limit* scoring events in chronological order."""
    if limit <= 0:
        return []
    return events[-limit:]


def resolve_summary_set_num(
    points_by_set: dict[Any, list[dict[str, Any]]] | None,
    current_set: int,
) -> int:
    """Return the set number the recap panel should display.

    ``current_set`` when it has any recorded ``add_point`` events,
    otherwise ``current_set - 1`` (clamped to 1) so the recap has
    something to show right after a set transition. Manual
    ``set_score`` edits to historical sets get tagged with the
    operator's current set via ``result.current_set`` and must not
    count as "this set has been played" — only ``add_point``
    records do.

    Shared between :class:`GameService` and :class:`Backend` to keep
    the resolution rule in one place.
    """
    try:
        cs = int(current_set)
    except (TypeError, ValueError):
        cs = 1
    if not points_by_set:
        return max(cs - 1, 1)
    current_events = (
        points_by_set.get(cs)
        or points_by_set.get(str(cs))
        or []
    )
    has_real_points = any(
        ev.get("action") == "add_point" for ev in current_events
    )
    return cs if has_real_points else max(cs - 1, 1)


def _points_by_set(
    events: list[dict[str, Any]],
    per_set_limit: int,
) -> dict[int, list[dict[str, Any]]]:
    """Group scoring events by set number, capped at *per_set_limit* per set.

    Used by the spectator (follow) page to render a navigable score-
    progression chart per set. Events without a ``set`` field (very
    old audit records) collapse into bucket ``0`` so the renderer can
    skip them cleanly.
    """
    out: dict[int, list[dict[str, Any]]] = {}
    for ev in events:
        set_num = ev.get("set")
        key = set_num if isinstance(set_num, int) and set_num > 0 else 0
        bucket = out.setdefault(key, [])
        if len(bucket) < per_set_limit:
            bucket.append(ev)
    out.pop(0, None)
    return out


def _timeouts_by_set(
    audit: list[dict[str, Any]],
    per_set_limit: int = 20,
) -> dict[int, list[dict[str, Any]]]:
    """Group ``add_timeout`` events by set number with their timestamps.

    Used by the spectator chart to render timeout markers on the
    same time axis as the points line. Each entry is a flat dict::

        {"team": 1, "set": 2, "ts": 1714508400.5}

    Per-set cap (default 20) protects the broadcast from runaway
    sizes — FIVB caps timeouts at 2 per team per set, so 20 is
    a comfortable safety margin that also tolerates legacy logs.
    """
    out: dict[int, list[dict[str, Any]]] = {}
    for r in audit:
        if _is_undo_record(r):
            continue
        if r.get("action") != "add_timeout":
            continue
        team = (r.get("params") or {}).get("team")
        if team not in (1, 2):
            continue
        ts = r.get("ts")
        set_num = _result_set(r)
        key = set_num if isinstance(set_num, int) and set_num > 0 else 0
        bucket = out.setdefault(key, [])
        if len(bucket) < per_set_limit:
            bucket.append({
                "team": team,
                "set": set_num,
                "ts": float(ts) if isinstance(ts, (int, float)) else None,
            })
    out.pop(0, None)
    return out


def _services_summary(
    audit: list[dict[str, Any]],
) -> dict[int, dict[str, int]]:
    """For each team, count rallies served and rallies won-while-serving.

    A "service won" is an ``add_point`` whose scoring team was already
    serving going into the rally. A "service lost" is a sideout — the
    serving team gives up the serve to the opponent. We don't know
    who served the very first rally of the match (no record carries
    a pre-state serve marker), so that single rally is unattributed.
    Every subsequent point is fully accounted for from the previous
    record's ``result.serve`` field, which encodes the *post-action*
    serve (= the team that will serve the next rally).
    """
    out: dict[int, dict[str, int]] = {
        1: {"served": 0, "won": 0},
        2: {"served": 0, "won": 0},
    }
    prev_post_serve: int | None = None
    for r in audit:
        if _is_undo_record(r):
            continue
        action = r.get("action")
        result = r.get("result") or {}

        if action == "add_point" and prev_post_serve in (1, 2):
            scoring = (r.get("params") or {}).get("team")
            if scoring in (1, 2):
                out[prev_post_serve]["served"] += 1
                if prev_post_serve == scoring:
                    out[prev_post_serve]["won"] += 1

        serve_str = result.get("serve")
        if serve_str == "A":
            prev_post_serve = 1
        elif serve_str == "B":
            prev_post_serve = 2
    return out


def _longest_streak_by_set(audit: list[dict[str, Any]]) -> dict[int, dict[int, int]]:
    """Longest consecutive ``add_point`` run per team in each set.

    The set-summary recap shows the *set's* highlight streak per
    team, so it needs the per-set breakdown rather than the match-
    wide :func:`_longest_streak`. A manual ``set_score`` edit or an
    opposite-team point both break the current run; once broken,
    we start counting again from 1. Output schema::

        { set_num: { 1: <home_longest>, 2: <away_longest> } }
    """
    by_set: dict[int, dict[int, int]] = {}
    streak_team: int | None = None
    streak_n = 0
    streak_set: int | None = None
    for r in audit:
        if _is_undo_record(r):
            continue
        action = r.get("action")
        set_num = _result_set(r)
        # Any non-point action resets the run — including set_score
        # edits, timeouts, and explicit reset events.
        if action != "add_point":
            streak_team, streak_n, streak_set = None, 0, None
            continue
        team = (r.get("params") or {}).get("team")
        if team not in (1, 2):
            continue
        # If the set rolled over, restart counting in the new set.
        if set_num != streak_set:
            streak_team = team
            streak_n = 1
            streak_set = set_num
        elif team == streak_team:
            streak_n += 1
        else:
            streak_team = team
            streak_n = 1
        if streak_set is None:
            continue
        bucket = by_set.setdefault(streak_set, {1: 0, 2: 0})
        if streak_n > bucket[team]:
            bucket[team] = streak_n
    return by_set


def _services_by_set(
    audit: list[dict[str, Any]],
) -> dict[int, dict[int, dict[str, int]]]:
    """Same ``served`` / ``won`` counts as :func:`_services_summary`
    but bucketed per set so a single-set recap can show each team's
    service hold rate for that set only. Output schema::

        { set_num: { 1: {"served": n, "won": m},
                     2: {"served": n, "won": m} } }
    """
    by_set: dict[int, dict[int, dict[str, int]]] = {}
    prev_post_serve: int | None = None
    for r in audit:
        if _is_undo_record(r):
            continue
        action = r.get("action")
        result = r.get("result") or {}
        if action == "add_point" and prev_post_serve in (1, 2):
            scoring = (r.get("params") or {}).get("team")
            if scoring in (1, 2):
                set_num = _result_set(r)
                if set_num is not None:
                    bucket = by_set.setdefault(set_num, {
                        1: {"served": 0, "won": 0},
                        2: {"served": 0, "won": 0},
                    })
                    bucket[prev_post_serve]["served"] += 1
                    if prev_post_serve == scoring:
                        bucket[prev_post_serve]["won"] += 1
        serve_str = result.get("serve")
        if serve_str == "A":
            prev_post_serve = 1
        elif serve_str == "B":
            prev_post_serve = 2
    return by_set


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
    events = _scoring_events(audit)
    return {
        "oid": oid,
        "audit_count": sum(1 for r in audit if not _is_undo_record(r)),
        "current_streak": _current_streak(audit),
        "longest_streak": base["longest_streak"],
        "set_win_comeback": base["set_win_comeback"],
        "partial_comeback": base["partial_comeback"],
        "longest_rally": base["longest_rally"],
        "total_points": base["total_points"],
        "set_durations": base["set_durations"],
        "points_history": _recent_points(events, history_limit),
        # Per-set buckets capped at 60 events (more than enough for
        # any indoor or beach set, including extreme deuce stretches).
        # Used by the spectator page to render past sets on demand.
        "points_by_set": _points_by_set(events, per_set_limit=60),
        # Per-set timeout events with timestamps so the spectator
        # chart can render them as markers on the same time axis.
        "timeouts_by_set": _timeouts_by_set(audit),
        # Services-won / services-total per team. The chart caption
        # uses these to label each side's hold rate.
        "services": _services_summary(audit),
        # Per-set variants of streak/services so the set-summary
        # recap can show stats that actually belong to the displayed
        # set instead of match-wide totals.
        "longest_streak_by_set": _longest_streak_by_set(audit),
        "services_by_set": _services_by_set(audit),
    }
