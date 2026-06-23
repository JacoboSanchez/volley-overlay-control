"""Match-rule presets for indoor / beach volleyball and table tennis.

A session has a ``mode`` ("indoor", "beach" or "table_tennis") plus
three numeric limits (``points_limit``, ``points_limit_last_set``,
``sets_limit``). The mode primarily drives:

* Default values for the limits (applied when the operator switches
  modes or asks for "reset to defaults").
* The interval used by the beach side-switch tracker — derived from
  the active set's points target: a 5-point cadence when the target
  is ≤15 (e.g. the deciding set), 7 otherwise.
* Whether the serve rotates automatically on a fixed cadence
  (table tennis) versus following the rally winner (volleyball).

Indoor:
  * 25 points per set (must win by 2)
  * 15 points in the deciding set
  * Best of 5
  * Side switch in the deciding set when the leading team first
    reaches the midpoint of its target (8 of 15). Computed entirely
    on the client as a transient alert — the backend just exposes
    the limits in ``config`` so the UI can derive the trigger.

Beach:
  * 21 points per set (must win by 2)
  * 15 points in the deciding set
  * Best of 3
  * Side switch every 7 points (every 5 in the tiebreak)

Table tennis:
  * 11 points per game (must win by 2)
  * 11 points in the deciding game
  * Best of 5 (selectable: 1 / 3 / 5 / 7)
  * Serve rotates every 2 points; every point once both players reach
    10 (deuce). The first server alternates each game. Ends switch
    after every game, and once a player reaches the midpoint (5) of
    the deciding game. The backend computes the live server and a
    serve-change countdown so the operator never tracks it by hand.
"""

from __future__ import annotations

from typing import Literal

MatchMode = Literal["indoor", "beach", "table_tennis"]

VALID_MODES: tuple[str, ...] = ("indoor", "beach", "table_tennis")


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
    "table_tennis": RulesPreset(
        points_limit=11, points_limit_last_set=11, sets_limit=5,
    ),
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


def compute_side_switch(
    *, mode: str, current_set: int, sets_limit: int,
    team1_score: int, team2_score: int,
    points_limit: int, points_limit_last_set: int,
) -> dict | None:
    """Return the beach side-switch indicator for the current set.

    Returns ``None`` for non-beach modes — callers attach the field
    only when present, so the indoor payload stays unchanged. (Indoor
    has a separate, transient deciding-set midpoint alert that the
    frontend computes from consecutive state diffs.)
    """
    if mode != "beach":
        return None
    interval = side_switch_interval(
        current_set=current_set, sets_limit=sets_limit,
        points_limit=points_limit, points_limit_last_set=points_limit_last_set,
    )
    points_in_set = max(0, int(team1_score)) + max(0, int(team2_score))
    # ``next_switch_at`` is the smallest multiple of *interval* that is
    # strictly greater than the current total — so when the total is
    # exactly on the boundary, we advance to the next one. This matches
    # the operator-facing semantic: "the switch for the previous N
    # points has just occurred; the next one is N more points away".
    if points_in_set == 0:
        next_switch_at = interval
    else:
        next_switch_at = ((points_in_set // interval) + 1) * interval
    return {
        "interval": interval,
        "points_in_set": points_in_set,
        "next_switch_at": next_switch_at,
        "points_until_switch": next_switch_at - points_in_set,
        # ``is_switch_pending`` flags the moment the most recent point
        # crossed a boundary — the operator should swap sides now.
        "is_switch_pending": (
            points_in_set > 0 and points_in_set % interval == 0
        ),
    }


def compute_sides_swapped_auto(
    *, mode: str, current_set: int, sets_limit: int,
    team1_score: int, team2_score: int,
    points_limit: int, points_limit_last_set: int,
    completed_set_scores: list[tuple[int, int]] | None = None,
) -> bool:
    """Auto-derived display-side swap parity for the live match state.

    Models the physical court: teams switch sides after every set;
    within a set, beach matches switch every
    :func:`side_switch_interval` combined points and indoor matches
    switch once in the deciding set when the leading team first
    reaches the midpoint (8 of a 15-point set). The result is the
    parity of *every* switch since the first serve — including the
    mid-set switches of already-completed sets, reconstructed from
    ``completed_set_scores`` (final ``(team1, team2)`` per finished
    set, in order) — so the rendered orientation tracks where the
    teams actually stand. Being a pure function of the score, an undo
    rewinds the orientation automatically.
    """
    completed = list(completed_set_scores or [])
    # One switch between consecutive sets.
    flips = max(0, current_set - 1)

    if mode == "beach":
        # Mid-set switches in completed sets…
        for idx, (s1, s2) in enumerate(completed, start=1):
            interval = side_switch_interval(
                current_set=idx, sets_limit=sets_limit,
                points_limit=points_limit,
                points_limit_last_set=points_limit_last_set,
            )
            flips += (max(0, int(s1)) + max(0, int(s2))) // interval
        # …and in the set currently being played.
        interval = side_switch_interval(
            current_set=current_set, sets_limit=sets_limit,
            points_limit=points_limit,
            points_limit_last_set=points_limit_last_set,
        )
        points_in_set = max(0, int(team1_score)) + max(0, int(team2_score))
        flips += points_in_set // interval
    elif mode == "table_tennis":
        # Table tennis: players switch ends after *every* game — already
        # captured by the one-flip-per-completed-set base above. The only
        # extra switch is in the deciding game, when a player first reaches
        # the midpoint of the target (5 of 11). Earlier games carry no
        # mid-game switch.
        if current_set >= sets_limit:
            midpoint = points_limit_last_set // 2
            if max(int(team1_score), int(team2_score)) >= midpoint:
                flips += 1
    elif current_set >= sets_limit:
        # Indoor deciding set: one switch when the leading team first
        # reaches the midpoint (FIVB: 8 of 15). Completed sets carry no
        # mid-set switches in indoor mode, and a completed deciding set
        # means the match is over — the final orientation just sticks.
        midpoint = (points_limit_last_set // 2) + 1
        if max(int(team1_score), int(team2_score)) >= midpoint:
            flips += 1

    return flips % 2 == 1


# -----------------------------------------------------------------------------
# Table-tennis serve rotation
# -----------------------------------------------------------------------------

def _other_team(team: int) -> int:
    return 2 if team == 1 else 1


def _tt_serve_turns(
    *, team1_score: int, team2_score: int, target: int,
) -> int:
    """Number of completed service turns at the current combined score.

    Before deuce a turn is two points; once both players reach
    ``target - 1`` (10 in an 11-point game) every point is its own
    turn. The server alternates on each turn, so the *parity* of this
    count decides who is on serve.
    """
    deuce_at = 2 * max(0, target - 1)
    points = max(0, int(team1_score)) + max(0, int(team2_score))
    if points < deuce_at:
        return points // 2
    return (deuce_at // 2) + (points - deuce_at)


def _tt_game_first_server(first_server: int, current_set: int) -> int:
    """Team that serves first in *current_set* — alternates each game."""
    if (current_set - 1) % 2 == 0:
        return first_server
    return _other_team(first_server)


def table_tennis_server(
    *, first_server: int, current_set: int, sets_limit: int,
    team1_score: int, team2_score: int,
    points_limit: int, points_limit_last_set: int,
) -> int:
    """Return the team (1 or 2) currently on serve in a table-tennis game.

    A pure function of the score, the match's ``first_server`` (the team
    that serves first in game 1) and the game index — so an undo rewinds
    the serve automatically. ``first_server`` alternates each game.
    """
    fs = first_server if first_server in (1, 2) else 1
    target = points_limit_last_set if current_set >= sets_limit else points_limit
    turns = _tt_serve_turns(
        team1_score=team1_score, team2_score=team2_score, target=target,
    )
    game_first = _tt_game_first_server(fs, current_set)
    return game_first if turns % 2 == 0 else _other_team(game_first)


def table_tennis_first_server_for(
    *, desired_server: int, current_set: int, sets_limit: int,
    team1_score: int, team2_score: int,
    points_limit: int, points_limit_last_set: int,
) -> int:
    """Invert :func:`table_tennis_server`.

    Given the team the operator wants on serve *right now*, return the
    match-level ``first_server`` that produces it under the current
    score/game — so clicking a serve toggle mid-game stays consistent
    with the rotation going forward.
    """
    target = points_limit_last_set if current_set >= sets_limit else points_limit
    turns = _tt_serve_turns(
        team1_score=team1_score, team2_score=team2_score, target=target,
    )
    game_first = desired_server if turns % 2 == 0 else _other_team(desired_server)
    if (current_set - 1) % 2 == 0:
        return game_first
    return _other_team(game_first)


def compute_serve_switch(
    *, mode: str, current_set: int, sets_limit: int,
    first_server: int, team1_score: int, team2_score: int,
    points_limit: int, points_limit_last_set: int,
) -> dict | None:
    """Serve-rotation countdown for the current table-tennis game.

    Returns ``None`` for non-table-tennis modes (where the serve follows
    the rally winner and there is nothing to count down). The shape
    mirrors the beach side-switch indicator: a countdown to the next
    serve change plus an ``is_change_pending`` flag that fires the moment
    the most recent point handed serve over.
    """
    if mode != "table_tennis":
        return None
    target = points_limit_last_set if current_set >= sets_limit else points_limit
    deuce_at = 2 * max(0, target - 1)
    points = max(0, int(team1_score)) + max(0, int(team2_score))
    if points < deuce_at:
        next_change_at = ((points // 2) + 1) * 2
        is_pending = points > 0 and points % 2 == 0
    else:
        # Past deuce every point flips the serve.
        next_change_at = points + 1
        is_pending = True
    server = table_tennis_server(
        first_server=first_server, current_set=current_set,
        sets_limit=sets_limit, team1_score=team1_score, team2_score=team2_score,
        points_limit=points_limit, points_limit_last_set=points_limit_last_set,
    )
    return {
        "server": server,
        "points_in_set": points,
        "next_change_at": next_change_at,
        "points_until_change": next_change_at - points,
        "is_change_pending": is_pending,
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
