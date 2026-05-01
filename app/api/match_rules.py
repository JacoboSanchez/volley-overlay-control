"""Match-rule presets for indoor vs. beach volleyball.

A session has a ``mode`` ("indoor" or "beach") plus three numeric
limits (``points_limit``, ``points_limit_last_set``, ``sets_limit``).
The mode primarily drives:

* Default values for the limits (applied when the operator switches
  modes or asks for "reset to defaults").
* The interval used by the beach side-switch tracker — derived from
  the active set's points target: a 5-point cadence when the target
  is ≤15 (e.g. the deciding set), 7 otherwise.

Indoor:
  * 25 points per set (must win by 2)
  * 15 points in the deciding set
  * Best of 5

Beach:
  * 21 points per set (must win by 2)
  * 15 points in the deciding set
  * Best of 3
  * Side switch every 7 points (every 5 in the tiebreak), plus a
    one-off switch in the deciding set when either team reaches the
    midpoint of its target (FIVB indoor 5th-set rule, applied here so
    operators get a dedicated alert at e.g. 8 of 15).
"""

from __future__ import annotations

from typing import Literal

MatchMode = Literal["indoor", "beach"]

VALID_MODES: tuple[str, ...] = ("indoor", "beach")


class RulesPreset:
    __slots__ = ("points_limit", "points_limit_last_set", "sets_limit")

    def __init__(
        self, points_limit: int, points_limit_last_set: int, sets_limit: int,
    ):
        self.points_limit = points_limit
        self.points_limit_last_set = points_limit_last_set
        self.sets_limit = sets_limit

    def as_dict(self) -> dict:
        return {
            "points_limit": self.points_limit,
            "points_limit_last_set": self.points_limit_last_set,
            "sets_limit": self.sets_limit,
        }


PRESETS: dict[str, RulesPreset] = {
    "indoor": RulesPreset(points_limit=25, points_limit_last_set=15, sets_limit=5),
    "beach":  RulesPreset(points_limit=21, points_limit_last_set=15, sets_limit=3),
}


def defaults_for(mode: str) -> RulesPreset:
    """Return the canonical ``RulesPreset`` for *mode*.

    Falls back to indoor when the mode is unrecognised — this keeps
    the rest of the codebase simple at the cost of silently coercing
    bad input. Callers that care should validate via :func:`is_valid_mode`
    first.
    """
    return PRESETS.get(mode, PRESETS["indoor"])


def is_valid_mode(mode: object) -> bool:
    return isinstance(mode, str) and mode in VALID_MODES


# -----------------------------------------------------------------------------
# Beach side-switch derivation
# -----------------------------------------------------------------------------

def _set_target(
    *, current_set: int, sets_limit: int,
    points_limit: int, points_limit_last_set: int,
) -> int:
    """Return the points target the *current* set is being played to."""
    return points_limit_last_set if current_set >= sets_limit else points_limit


def side_switch_interval(
    *, current_set: int, sets_limit: int,
    points_limit: int, points_limit_last_set: int,
) -> int:
    """Points scored (combined) between side switches.

    Driven by the active set's points target rather than its position
    in the match: a 5-point cadence for short sets (target ≤15, e.g.
    the deciding set) and 7 for longer sets (target >15). For the
    standard beach preset (21 / 15) this matches the previous
    "every-7, every-5-in-tiebreak" behaviour exactly.
    """
    target = _set_target(
        current_set=current_set, sets_limit=sets_limit,
        points_limit=points_limit, points_limit_last_set=points_limit_last_set,
    )
    return 5 if target <= 15 else 7


def _last_set_midpoint(points_limit_last_set: int) -> int:
    """Half of the deciding-set target, rounded up (15 → 8).

    Returns 0 for non-positive targets so callers can use it as a
    "midpoint rule disabled" sentinel without an extra branch.
    """
    if points_limit_last_set <= 0:
        return 0
    return (points_limit_last_set + 1) // 2


def compute_side_switch(
    *, mode: str, current_set: int, sets_limit: int,
    team1_score: int, team2_score: int,
    points_limit: int, points_limit_last_set: int,
) -> dict | None:
    """Return the beach side-switch indicator for the current set.

    Returns ``None`` for non-beach modes — callers attach the field
    only when present, so the indoor payload stays unchanged.

    The pending flag fires for two reasons, OR-ed together:

    * Combined-cadence boundary: the current combined score is a
      non-zero multiple of ``interval``.
    * Deciding-set midpoint: in the last set, when the leading team
      first reaches ``ceil(points_limit_last_set / 2)`` (8 for 15).
      The flag stays on until the trailing team also reaches that
      score — at which point both have crossed and the alert clears.
    """
    if mode != "beach":
        return None
    interval = side_switch_interval(
        current_set=current_set, sets_limit=sets_limit,
        points_limit=points_limit, points_limit_last_set=points_limit_last_set,
    )
    t1 = max(0, int(team1_score))
    t2 = max(0, int(team2_score))
    points_in_set = t1 + t2
    # ``next_switch_at`` is the smallest multiple of *interval* that is
    # strictly greater than the current total — so when the total is
    # exactly on the boundary, we advance to the next one. This matches
    # the operator-facing semantic: "the switch for the previous N
    # points has just occurred; the next one is N more points away".
    if points_in_set == 0:
        next_switch_at = interval
    else:
        next_switch_at = ((points_in_set // interval) + 1) * interval
    cadence_pending = points_in_set > 0 and points_in_set % interval == 0

    # Deciding-set midpoint rule (FIVB indoor 5th-set semantic). Fires
    # while exactly one team sits on the midpoint score, mirroring the
    # one-shot "swap when leader hits 8" trigger. Once both teams have
    # reached it the alert clears — there's no second switch this set.
    is_last_set = current_set >= sets_limit
    midpoint = _last_set_midpoint(points_limit_last_set) if is_last_set else 0
    midpoint_pending = (
        is_last_set and midpoint > 0
        and max(t1, t2) == midpoint and min(t1, t2) < midpoint
    )

    return {
        "interval": interval,
        "points_in_set": points_in_set,
        "next_switch_at": next_switch_at,
        "points_until_switch": next_switch_at - points_in_set,
        # ``is_switch_pending`` flags the moment the most recent point
        # crossed a boundary — the operator should swap sides now.
        "is_switch_pending": cadence_pending or midpoint_pending,
    }


# -----------------------------------------------------------------------------
# Set-point / match-point derivation
# -----------------------------------------------------------------------------

def _team_has_set_point(
    team_score: int, rival_score: int, points_limit: int,
) -> bool:
    """Return ``True`` if scoring one more point would close out the set.

    Mirrors :meth:`GameManager._is_winning_score` applied to
    ``team_score + 1``: a point is set-winning when the team reaches
    ``points_limit`` *and* leads by more than 1. The ``> 1`` margin
    rule is what guarantees that, even on the boundary, at most one
    side can hold set point at any instant (a 24-24 deuce gives
    neither side set point).
    """
    return team_score + 1 >= points_limit and (team_score + 1) - rival_score > 1


def compute_match_point_info(
    *, current_set: int, sets_limit: int,
    team1_sets: int, team2_sets: int,
    team1_score: int, team2_score: int,
    points_limit: int, points_limit_last_set: int,
    match_finished: bool,
) -> dict:
    """Per-team flags signalling that the next point would close out the
    current set or the entire match.

    Returns a dict with four boolean fields. When the match is already
    finished, every flag is ``False`` — the caller's
    ``match_finished`` flag takes visual precedence anyway, and clamping
    here keeps the indicator from briefly flashing during the
    set-end → match-end transition.

    Match point implies set point, but the renderer is expected to show
    only the more specific label (match point) when both apply.
    """
    if match_finished:
        return {
            "team_1_set_point": False,
            "team_2_set_point": False,
            "team_1_match_point": False,
            "team_2_match_point": False,
        }

    # The deciding set has its own point cap (e.g. 15 in the tiebreak);
    # any earlier set uses ``points_limit``.
    is_last_set = current_set >= sets_limit
    set_target = points_limit_last_set if is_last_set else points_limit

    t1_set = _team_has_set_point(team1_score, team2_score, set_target)
    t2_set = _team_has_set_point(team2_score, team1_score, set_target)

    # Match point: holding set point AND winning the current set would
    # clinch the match. ``soft_limit`` mirrors GameManager.match_finished.
    soft_limit = sets_limit // 2 + 1
    t1_match = t1_set and (team1_sets + 1) >= soft_limit
    t2_match = t2_set and (team2_sets + 1) >= soft_limit

    return {
        "team_1_set_point": t1_set,
        "team_2_set_point": t2_set,
        "team_1_match_point": t1_match,
        "team_2_match_point": t2_match,
    }
