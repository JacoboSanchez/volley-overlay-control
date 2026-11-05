"""Rebuild match state from the audit log, and check it against live state.

The audit log is append-only and every state-mutating action records a
post-state snapshot (see :func:`app.api.game_audit_hooks.audit`)::

    {"current_set": 2, "score_set": 1, "match_finished": false,
     "team_1": {"sets": 1, "score": 25, "timeouts": 0},
     "team_2": {"sets": 0, "score": 20, "timeouts": 1},
     "serve": "A"}

``score_set`` is the set the action scored in (the set a set-winning point
closed, even though ``current_set`` has already advanced), and the
``timeouts`` counts describe that same set. Folding those
snapshots over the tombstone-filtered log therefore reproduces the match
without re-running any volleyball rule: the history *is* the state. That
makes the log usable as the source of truth for three things:

* **Verification** — :func:`check_consistency` compares the replay with the
  live :class:`~app.state.State` and names every field that drifted (an
  audit append that failed, a mutation path that forgot to audit). Exposed
  as ``GET /api/v1/audit/consistency``.
* **Recovery** — :func:`replay` is a pure function from records to a
  ``State``; a lost or corrupted state row can be rebuilt from history.
* **Reconciliation** — an offline client can replay its queued actions'
  snapshots against the server's history instead of trusting a FIFO.

It is a drift *detector*, not a proof: every snapshot is absolute for its
set, so the fold is "last snapshot per set wins". A missing or wrongly hidden
record is caught while it is the newest word on its set (or on sets won,
the current set, timeouts or serve); a later record about the same set
masks it. That is exactly the window a live scoreboard cares about.

Two limits are inherent and reported rather than hidden:

* Retention pruning (``AUDIT_LOG_MAX_BYTES``) can drop the start of a long
  match. Sets no surviving record scored in are *uncovered*: listed in
  :attr:`ReplayResult.covered_sets` by omission and never reported as
  divergent.
* ``reset`` clears the log before recording itself, so a log that starts
  with ``reset`` is known to be complete (:attr:`ReplayResult.starts_at_reset`).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from app.state import Serve, State

#: Actions whose records only annotate the timeline; their snapshot is still
#: a valid post-state, so they are folded like any other record.
_RESET_ACTION = "reset"
_SET_SCORE_ACTION = "set_score"


@dataclass
class ReplayResult:
    """Outcome of folding an audit log into a :class:`State`."""

    state: State
    records: int = 0
    starts_at_reset: bool = False
    covered_sets: set[int] = field(default_factory=set)
    timeout_sets: set[int] = field(default_factory=set)
    skipped: int = 0


@dataclass(frozen=True)
class Divergence:
    """One field where the replayed state disagrees with the live one."""

    field: str
    replayed: Any
    live: Any
    set_number: int | None = None
    team: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "set_number": self.set_number,
            "team": self.team,
            "replayed": self.replayed,
            "live": self.live,
        }


def _valid_set(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if 1 <= number <= State.MAX_SETS else None


def _team_snapshot(result: dict, team: int) -> dict | None:
    snapshot = result.get(f"team_{team}")
    return snapshot if isinstance(snapshot, dict) else None


def _apply(result_state: ReplayResult, record: dict) -> bool:
    """Fold one record into *result_state*. Returns False when skipped."""
    state = result_state.state
    action = record.get("action")
    result = record.get("result")
    if not isinstance(result, dict):
        return False
    current_set = _valid_set(result.get("current_set"))
    if current_set is None:
        return False
    score_set = _valid_set(result.get("score_set", current_set)) or current_set
    teams = [_team_snapshot(result, team) for team in (1, 2)]
    if any(snapshot is None for snapshot in teams):
        return False

    if action == _SET_SCORE_ACTION:
        # A manual correction may target a set other than the current one;
        # the snapshot only covers ``score_set`` (the current set), so the
        # edited value comes from the params.
        params = record.get("params") or {}
        edited_set = _valid_set(params.get("set_number"))
        team = params.get("team")
        if edited_set is not None and team in (1, 2):
            try:
                state.set_game(edited_set, team, int(params.get("value", 0)))
            except (TypeError, ValueError):
                pass
            else:
                result_state.covered_sets.add(edited_set)

    for team, snapshot in zip((1, 2), teams, strict=True):
        assert snapshot is not None
        state.set_game(score_set, team, int(snapshot.get("score", 0)))
        state.set_sets(team, int(snapshot.get("sets", 0)))
        # The hook reads timeouts from the state's own current set, which is
        # still ``score_set`` when a set-winning point is audited.
        state.set_timeout(team, int(snapshot.get("timeouts", 0)), score_set)
    state.set_current_set(current_set)
    state.set_current_serve(State._parse_serve(result.get("serve", Serve.NONE.value)))
    result_state.covered_sets.add(score_set)
    result_state.timeout_sets.add(score_set)
    return True


def replay(records: Iterable[dict]) -> ReplayResult:
    """Fold tombstone-filtered audit *records* (oldest first) into a state.

    Pure: no I/O, no rules engine. A ``reset`` record restarts the fold from
    a blank state, so replaying a log that spans several matches yields the
    latest one. Records without a usable snapshot are counted in
    :attr:`ReplayResult.skipped` and ignored.
    """
    out = ReplayResult(state=State())
    first = True
    for record in records:
        if not isinstance(record, dict):
            continue
        if record.get("action") == _RESET_ACTION:
            out = ReplayResult(state=State(), records=out.records, skipped=out.skipped)
            out.starts_at_reset = True
        elif first:
            out.starts_at_reset = False
        first = False
        out.records += 1
        if not _apply(out, record):
            out.skipped += 1
    return out


def compare(
    replayed: ReplayResult, live: State, *, compare_serve: bool = True,
) -> list[Divergence]:
    """List the fields where *live* disagrees with the replay.

    Only what the history covers is compared: per-set scores for
    :attr:`ReplayResult.covered_sets`, per-set timeouts for the sets a
    snapshot reported them in, plus sets won, the current set and the
    serve. An empty log yields no divergences — there is nothing to check.

    Pass ``compare_serve=False`` where the serve is derived rather than
    recorded (table tennis rotates it in ``get_state``, after the snapshot
    is taken).
    """
    if replayed.records - replayed.skipped <= 0:
        return []
    rs = replayed.state
    out: list[Divergence] = []
    if rs.get_current_set() != live.get_current_set():
        out.append(Divergence("current_set", rs.get_current_set(), live.get_current_set()))
    if compare_serve and rs.get_current_serve() != live.get_current_serve():
        out.append(
            Divergence("serve", rs.get_current_serve().value, live.get_current_serve().value)
        )
    for team in (1, 2):
        if rs.get_sets(team) != live.get_sets(team):
            out.append(Divergence("sets", rs.get_sets(team), live.get_sets(team), team=team))
        for set_number in sorted(replayed.covered_sets):
            a, b = rs.get_game(team, set_number), live.get_game(team, set_number)
            if a != b:
                out.append(Divergence("score", a, b, set_number=set_number, team=team))
        for set_number in sorted(replayed.timeout_sets):
            a, b = rs.get_timeout(team, set_number), live.get_timeout(team, set_number)
            if a != b:
                out.append(Divergence("timeouts", a, b, set_number=set_number, team=team))
    return out


def check_consistency(
    records: Iterable[dict], live: State, *, compare_serve: bool = True,
) -> dict[str, Any]:
    """Replay *records* and compare with *live*; JSON-ready summary."""
    replayed = replay(records)
    divergences = compare(replayed, live, compare_serve=compare_serve)
    return {
        "consistent": not divergences,
        "records": replayed.records,
        "skipped": replayed.skipped,
        "starts_at_reset": replayed.starts_at_reset,
        "covered_sets": sorted(replayed.covered_sets),
        "divergences": [d.as_dict() for d in divergences],
    }
