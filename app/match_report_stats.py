"""Pure audit-log reducers behind the match report and live stats.

Split out of :mod:`app.match_report`. Everything here derives from the
archived audit log alone — no I/O, no request context — so the report
stays reproducible from the snapshot.
"""

from __future__ import annotations

from typing import Any, overload

from app.api.schemas import ERROR_TYPES, POINT_TYPES

# ---------------------------------------------------------------------------
# Audit-log derived helpers (running score, undo collapse, stats, charts)
# ---------------------------------------------------------------------------

def _coerce_int(raw: object) -> int | None:
    """Best-effort ``int`` parse for audit-record numeric fields.

    Accepts a real ``int`` directly or a string of digits (some
    archive paths stringify scores). Returns ``None`` for anything
    else. Caller decides whether to apply a positivity filter.
    """
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.isdigit():
        return int(raw)
    return None


@overload
def _safe_int(value: object) -> int | None: ...
@overload
def _safe_int(value: object, default: int) -> int: ...
@overload
def _safe_int(value: object, default: None) -> int | None: ...


def _safe_int(value: object, default: int | None = None) -> int | None:
    """Lenient ``int`` parse: like ``int(value)`` but returns *default* on failure.

    Stricter callers should prefer :func:`_coerce_int`; this helper
    mirrors the inline ``try: int(value) except (TypeError, ValueError)``
    pattern that recurs across set/score parsing.
    """
    try:
        return int(value)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return default


def _result_score(record: dict, team: int) -> int | None:
    """Pull the post-action score for *team* out of an audit ``result`` blob."""
    block = (record.get("result") or {}).get(f"team_{team}") or {}
    return _coerce_int(block.get("score"))


def _result_set(record: dict) -> int | None:
    """Set number this audit record applies to (1-indexed).

    Prefers ``result.score_set`` when present: a set-winning
    ``add_point`` advances ``current_set`` to the next set, but the
    scores in the record (e.g. 25-23) belong to the *previous* set,
    and ``score_set`` tags that explicitly. Falls back to
    ``current_set`` for older audit records that predate the
    ``score_set`` field.
    """
    result = record.get("result") or {}
    for key in ("score_set", "current_set"):
        n = _coerce_int(result.get(key))
        if n is not None and n > 0:
            return n
    return None


def _is_score_action(record: dict) -> bool:
    return record.get("action") in ("add_point", "set_score")


def _first_scoring_index(audit: list[dict]) -> int | None:
    """Index of the first non-undo ``add_point`` / ``set_score`` record.

    The audit log starts with whatever the operator did first — often a
    ``reset`` to clear the previous match's state — but a "match" only
    really begins once someone scores. Until the UI exposes a dedicated
    "match start" marker, every report-side time anchor (relative
    timestamps, duration, set durations, stats) snaps to this index.
    Returns ``None`` when the audit has no scoring action at all.
    """
    for index, record in enumerate(audit):
        if (record.get("params") or {}).get("undo"):
            continue
        if _is_score_action(record):
            return index
    return None


def _trim_pregame(audit: list[dict]) -> list[dict]:
    """Drop pre-first-scoring records (``reset``, stray timeouts, …).

    Keeps everything from the first scoring action onward. When the
    audit has no scoring action at all we return ``[]`` — the timeline
    renderer already understands the empty case and shows "no audit
    records", and falling through to the unfiltered list would let the
    pregame noise leak back into the report.
    """
    idx = _first_scoring_index(audit)
    return audit[idx:] if idx is not None else []


def _played_set_count(final_state: dict, fallback: int) -> int:
    """Highest set N with non-zero scoring data, clamped to *fallback*.

    The match-history archive bundles ``team_X.scores.set_N`` for every
    set up to ``sets_limit``, even sets that were never played (best
    of 3 ending 2-0 still has ``set_3``: 0/0). Render only the sets
    that actually saw points so empty trailing columns don't dilute
    the report. When no set has scores yet (fresh archive) we collapse
    to a single set frame rather than painting all ``sets_limit``
    columns full of ``—``s.

    *fallback* is honoured only as an upper bound — corrupt snapshots
    reporting set N > sets_limit shouldn't paint a column the rules
    don't allow.
    """
    teams = (final_state.get("team_1") or {}, final_state.get("team_2") or {})
    highest = 0
    for team in teams:
        scores = team.get("scores") or {}
        for key, value in scores.items():
            if not isinstance(key, str) or not key.startswith("set_"):
                continue
            n = _safe_int(key.removeprefix("set_"))
            if n is None:
                continue
            v = 0 if value is None else _safe_int(value, 0)
            if v > 0:
                highest = max(highest, n)
    if highest == 0:
        return 1
    return min(highest, fallback) if fallback > 0 else highest


def _collapse_undos(audit: list[dict]) -> list[dict]:
    """Drop both halves of every ``undo`` pair from the rendered
    timeline so undone actions never appear in the report.

    Two cases reach this function:

    * Live unified-undo logs (the common case), where
      ``action_log.pop_last_forward`` already removed the original
      forward physically and the audit-log just carries the
      trailing undo record. The orphan undo is dropped because
      the action it referenced no longer exists.
    * Legacy / archived audit logs that still hold both a forward
      record and the explicit undo that reversed it — typically
      from pre-unification snapshots or replay-style fixtures. We
      walk back to the most recent matching forward by
      ``(action, team)`` and remove **both** the forward and the
      undo, mirroring the live behaviour.

    Net result: the report renders "as if the undone action never
    happened". State-level aggregates already reflect the inverse
    (the score / set / timeout counters never recorded the popped
    increment), so the timeline can stay equally clean.
    """
    out: list[dict] = []
    for record in audit:
        params = record.get("params") or {}
        if not params.get("undo"):
            out.append(dict(record))
            continue
        # Walk back for the most recent forward record with the same
        # ``(action, team)`` and remove it. The undo itself never
        # reaches the output either — both halves disappear.
        action = record.get("action")
        team = params.get("team")
        for index in range(len(out) - 1, -1, -1):
            prior = out[index]
            prior_params = prior.get("params") or {}
            if (
                prior.get("action") == action
                and prior_params.get("team") == team
                and not prior_params.get("undo")
            ):
                del out[index]
                break
        # No matching forward → orphan undo. Already not appended
        # above; nothing else to do.
    return out


def _set_durations_from_audit(audit: list[dict]) -> dict[int, float]:
    """Per-set duration in seconds derived from audit timestamps.

    For each set we take ``max_ts - min_ts`` over records whose
    ``current_set`` matches. Sets with fewer than two timestamps fall
    out of the result map (no meaningful duration).
    """
    by_set: dict[int, list[float]] = {}
    for record in audit:
        if record.get("params", {}).get("undo"):
            continue
        set_num = _result_set(record)
        ts = record.get("ts")
        if set_num is None or not isinstance(ts, (int, float)):
            continue
        by_set.setdefault(set_num, []).append(float(ts))
    durations: dict[int, float] = {}
    for set_num, stamps in by_set.items():
        if len(stamps) < 2:
            continue
        durations[set_num] = max(stamps) - min(stamps)
    return durations


def _running_score_pair(record: dict) -> tuple[int, int] | None:
    """``(team1, team2)`` running score after this audit record, if known."""
    s1 = _result_score(record, 1)
    s2 = _result_score(record, 2)
    if s1 is None or s2 is None:
        return None
    return (s1, s2)


def _timeouts_per_set(audit: list[dict]) -> dict[int, dict[int, int]]:
    """Count ``add_timeout`` actions per (set, team) from the audit log.

    The live snapshot's ``team_X.timeouts`` is the current set's count,
    so reconstructing the full per-set table for the printed report
    requires walking the audit log (each ``add_timeout`` record
    carries the set it landed in via ``result.current_set``). Returns
    ``{set_num: {team: count}}``; callers consult
    ``.get(set, {}).get(team, 0)`` for safe lookup.
    """
    out: dict[int, dict[int, int]] = {}
    for record in audit:
        if record.get("action") != "add_timeout":
            continue
        params = record.get("params") or {}
        if params.get("undo"):
            continue
        team = params.get("team")
        set_num = _result_set(record)
        if team not in (1, 2) or set_num is None:
            continue
        out.setdefault(set_num, {}).setdefault(team, 0)
        out[set_num][team] += 1
    return out


_SERVE_TO_TEAM = {"A": 1, "B": 2}


def _initial_serve_from_pregame(raw_audit: list[dict]) -> int | None:
    """Serve holder going into the first rally, from the *untrimmed* log.

    ``_trim_pregame`` drops everything before the first scored point —
    including the operator's pre-match ``change_serve`` that says who
    serves first. Without that seed the first rally of the match can
    never be attributed to a server. Scan the pregame slice backwards
    for the most recent record that snapshots a serve: ``"A"``/``"B"``
    map to a team, any other present value (e.g. ``"None"`` after a
    reset) means the serve was explicitly cleared — return ``None``
    rather than resurrecting an older, superseded serve. Records
    without the key (legacy logs) are skipped.
    """
    idx = _first_scoring_index(raw_audit)
    if idx is None:
        return None
    for record in reversed(raw_audit[:idx]):
        result = record.get("result") or {}
        if "serve" not in result:
            continue
        serve = result.get("serve")
        return _SERVE_TO_TEAM.get(serve) if isinstance(serve, str) else None
    return None


def _serve_receive_summary(
    audit: list[dict],
    initial_serve: int | None = None,
) -> dict[int, dict[str, int]]:
    """Rallies served / won-while-serving per team, from the audit log.

    Returns ``{1: {"served": n, "won": m}, 2: {...}}``. Mirrors the
    live-stats ``_services_summary`` walk (:mod:`app.api.live_stats`)
    so the printed report reconciles with the live endpoint: every
    record's ``result.serve`` is the *post-action* snapshot, so the
    team serving rally N is the serve recorded after record N-1.
    *initial_serve* seeds the tracker for the first rally (see
    :func:`_initial_serve_from_pregame`). Rallies whose server is
    unknown — before the tracker arms, or legacy logs that never
    recorded a serve — are excluded from both counters, so derived
    percentages never guess. A team's points won on *receive*
    (side-outs) fall out as the opponent's ``served - won``.
    """
    out: dict[int, dict[str, int]] = {
        1: {"served": 0, "won": 0},
        2: {"served": 0, "won": 0},
    }
    prev_post_serve = initial_serve if initial_serve in (1, 2) else None
    for record in audit:
        if (record.get("params") or {}).get("undo"):
            continue
        result = record.get("result") or {}

        if record.get("action") == "add_point" and prev_post_serve in (1, 2):
            scoring = (record.get("params") or {}).get("team")
            if scoring in (1, 2):
                out[prev_post_serve]["served"] += 1
                if prev_post_serve == scoring:
                    out[prev_post_serve]["won"] += 1

        # Update the tracker from this record's post-action snapshot.
        # Only ``"A"``/``"B"`` move it — a missing key or ``"None"``
        # (mid-match reset) leaves the last known server in place,
        # matching the live-stats semantics exactly.
        serve = result.get("serve")
        next_serve = (
            _SERVE_TO_TEAM.get(serve) if isinstance(serve, str) else None
        )
        if next_serve is not None:
            prev_post_serve = next_serve
    return out


def _record_point_tags(
    team: int,
    params: dict,
    set_num: int,
    point_types: dict[int, dict[str, int]],
    error_types: dict[int, dict[str, int]],
    point_types_by_set: dict[int, dict[int, dict[str, int]]],
) -> None:
    """Tally the optional scouting tags of one forward ``add_point``.

    Mutates the three accumulators in place. Untyped points are a
    no-op; ``error_type`` only counts under a tagged ``opp_error``.
    """
    pt = params.get("point_type")
    if pt not in point_types[team]:
        return
    point_types[team][pt] += 1
    pts_set = point_types_by_set.setdefault(
        set_num,
        {
            1: dict.fromkeys(POINT_TYPES, 0),
            2: dict.fromkeys(POINT_TYPES, 0),
        },
    )
    pts_set[team][pt] += 1
    if pt == "opp_error":
        et = params.get("error_type")
        if et in error_types[team]:
            error_types[team][et] += 1


def _update_biggest_lead(
    set_records: list[dict], set_num: int, biggest_lead: dict[int, dict],
) -> None:
    """Fold one set's running scores into the per-team biggest-lead map.

    Mutates *biggest_lead* (``{team: {"lead", "set"}}``) in place with
    the largest positive gap either team opened in this set.
    """
    for r in set_records:
        pair = _running_score_pair(r)
        if not pair:
            continue
        t1, t2 = pair
        if t1 - t2 > biggest_lead[1]["lead"]:
            biggest_lead[1] = {"lead": t1 - t2, "set": set_num}
        if t2 - t1 > biggest_lead[2]["lead"]:
            biggest_lead[2] = {"lead": t2 - t1, "set": set_num}


def _comeback_extremes(set_records: list[dict], winner: int) -> tuple[int, int]:
    """Walk one set's running scores; return comeback extremes.

    Returns ``(winner_peak_deficit, loser_max_recovery)``:

    * the largest deficit the eventual set winner faced (their
      ``set_win`` comeback), and
    * the largest deficit reduction the loser managed after actually
      trailing (their ``partial`` comeback).
    """
    winner_peak_deficit = 0
    loser_peak_deficit = 0
    loser_min_after_peak = 0
    loser_max_recovery = 0
    for r in set_records:
        pair = _running_score_pair(r)
        if not pair:
            continue
        t1, t2 = pair
        winner_deficit = (t2 - t1) if winner == 1 else (t1 - t2)
        loser_deficit = -winner_deficit
        if winner_deficit > winner_peak_deficit:
            winner_peak_deficit = winner_deficit
        if loser_deficit > loser_peak_deficit:
            loser_peak_deficit = loser_deficit
            loser_min_after_peak = loser_deficit
        elif loser_peak_deficit > 0:
            # Only count "recovery" once the loser has actually
            # trailed. Otherwise a team that led 5-0 from the
            # start and then collapsed would post a phantom
            # 5-point partial comeback — they never erased
            # anything, they just bled their early lead.
            # Clamp at 0: the comeback ends at the tie. A loser
            # who briefly took a lead mid-set still gets credit
            # for "points recovered while trailing" up to the
            # tying point, but the subsequent lead points are a
            # separate (and short-lived) story.
            clamped = max(0, loser_deficit)
            if clamped < loser_min_after_peak:
                loser_min_after_peak = clamped
                recovery = loser_peak_deficit - loser_min_after_peak
                if recovery > loser_max_recovery:
                    loser_max_recovery = recovery
    return winner_peak_deficit, loser_max_recovery


def _longest_scoring_gap(set_records: list[dict]) -> float:
    """Largest time gap between consecutive ``add_point`` records.

    A proxy for "longest rally" — without ball-in-play
    instrumentation that's the closest the audit log can give us.
    Restricted to ``add_point`` only: a manual ``set_score`` override
    is an editorial action (operator correcting a score after the
    fact) and including it would report the *editing* delay as a
    rally. The audit log is append-only so ``set_records`` is already
    in chronological order — no extra sort needed. Returns ``0.0``
    when the set has fewer than two timestamped points.
    """
    scoring_ts: list[float] = []
    for r in set_records:
        if r.get("action") != "add_point":
            continue
        ts = r.get("ts")
        if isinstance(ts, (int, float)):
            scoring_ts.append(float(ts))
    longest = 0.0
    for i in range(1, len(scoring_ts)):
        delta = scoring_ts[i] - scoring_ts[i - 1]
        if delta > longest:
            longest = delta
    return longest


def _compute_stats(audit: list[dict], *, initial_serve: int | None = None) -> dict:
    """Compute the Highlights block (longest streak, biggest comeback, totals).

    All metrics derive purely from the audit log so the report stays
    consistent with the "scoring trajectory" the audit promises. Set
    points are scored per-set. Comebacks are tracked per-team and
    split into two flavours:

    * ``set_win``: the largest deficit a team erased *and* went on to
      win the set with — i.e. the deficit faced by the eventual set
      winner.
    * ``partial``: the largest deficit reduction (peak deficit minus
      the smallest subsequent deficit) achieved by a team that
      ultimately *lost* the set. This surfaces near-comebacks that
      didn't quite finish.

    Storing both per team lets the renderer detect a tie when both
    sides happen to share the same maximum.

    *initial_serve* seeds the serve/receive walk for the first rally
    (see :func:`_initial_serve_from_pregame`); callers that don't
    track serve (e.g. live stats) simply omit it.
    """
    longest_streak: dict[str, Any] = {"team": None, "n": 0, "set": None}
    # Per-team peak deficit erased by the eventual set winner.
    set_win_comeback: dict[int, dict] = {
        1: {"deficit": 0, "set": None},
        2: {"deficit": 0, "set": None},
    }
    # Per-team peak deficit reduction by a losing team (partial recovery).
    partial_comeback: dict[int, dict] = {
        1: {"deficit": 0, "set": None},
        2: {"deficit": 0, "set": None},
    }
    # Per-team largest score gap opened at any point, with the set it
    # happened in. Independent of who finally won the set — the
    # comeback cards tell the "and then lost it" story.
    biggest_lead: dict[int, dict] = {
        1: {"lead": 0, "set": None},
        2: {"lead": 0, "set": None},
    }
    longest_rally: dict[str, Any] = {"duration_s": 0.0, "set": None}
    total_points = 0
    # Per-team total of won rallies (every ``add_point`` for the team,
    # tagged or not), used as the denominator for the point-composition
    # percentages in the report.
    total_points_by_team: dict[int, int] = {1: 0, 2: 0}
    # Optional per-point classification tallies (opt-in scouting tags).
    # ``point_types`` counts every tagged forward point per team;
    # ``error_types`` breaks the ``opp_error`` total into its specific
    # causes (a subset of opp_error — untyped opp_errors aren't here).
    point_types: dict[int, dict[str, int]] = {
        1: dict.fromkeys(POINT_TYPES, 0),
        2: dict.fromkeys(POINT_TYPES, 0),
    }
    error_types: dict[int, dict[str, int]] = {
        1: dict.fromkeys(ERROR_TYPES, 0),
        2: dict.fromkeys(ERROR_TYPES, 0),
    }
    # Per-set point-type tallies, so the set-summary recap can scope the
    # breakdown to the displayed set (same pattern as the per-set streak
    # / services variants). Only sets that have a tagged point appear.
    point_types_by_set: dict[int, dict[int, dict[str, int]]] = {}

    by_set: dict[int, list[dict]] = {}
    for record in audit:
        if record.get("params", {}).get("undo"):
            continue
        set_num = _result_set(record)
        if set_num is None:
            continue
        by_set.setdefault(set_num, []).append(record)

    for set_num, set_records in by_set.items():
        # Longest streak: count consecutive ``add_point`` actions by
        # the same team. Manual set_score breaks the streak.
        streak_team: int | None = None
        streak_n = 0
        for r in set_records:
            if r.get("action") != "add_point":
                streak_team, streak_n = None, 0
                continue
            team = (r.get("params") or {}).get("team")
            if team == streak_team:
                streak_n += 1
            else:
                streak_team, streak_n = team, 1
            if streak_n > longest_streak["n"]:
                longest_streak = {"team": team, "n": streak_n, "set": set_num}
            total_points += 1
            if team in (1, 2):
                total_points_by_team[team] += 1
                _record_point_tags(
                    team, r.get("params") or {}, set_num,
                    point_types, error_types, point_types_by_set,
                )

        # Biggest lead: largest gap either team opened in this set.
        _update_biggest_lead(set_records, set_num, biggest_lead)

        # Comebacks. Walk the running scores once, then split:
        #   * winner's peak deficit  → set_win comeback for the winner
        #   * loser's peak deficit minus the smallest subsequent deficit
        #     → partial comeback for the loser (they trimmed the gap
        #     but didn't close it).
        if not set_records:
            continue
        last_score = _running_score_pair(set_records[-1])
        if not last_score:
            continue
        winner = 1 if last_score[0] > last_score[1] else 2
        loser = 2 if winner == 1 else 1
        winner_peak_deficit, loser_max_recovery = _comeback_extremes(
            set_records, winner,
        )
        if winner_peak_deficit > set_win_comeback[winner]["deficit"]:
            set_win_comeback[winner] = {
                "deficit": winner_peak_deficit, "set": set_num,
            }
        if loser_max_recovery > partial_comeback[loser]["deficit"]:
            partial_comeback[loser] = {
                "deficit": loser_max_recovery, "set": set_num,
            }

        # Longest rally: see ``_longest_scoring_gap`` for the proxy
        # semantics (gap between consecutive ``add_point`` records).
        gap = _longest_scoring_gap(set_records)
        if gap > longest_rally["duration_s"]:
            longest_rally = {"duration_s": gap, "set": set_num}

    return {
        "longest_streak": longest_streak,
        "set_win_comeback": set_win_comeback,
        "partial_comeback": partial_comeback,
        "biggest_lead": biggest_lead,
        "longest_rally": longest_rally,
        "total_points": total_points,
        "total_points_by_team": total_points_by_team,
        "set_durations": _set_durations_from_audit(audit),
        "point_types": point_types,
        "error_types": error_types,
        "point_types_by_set": point_types_by_set,
        "serve_receive": _serve_receive_summary(audit, initial_serve),
    }


