"""Rapid-pair undo correction for consecutive add_point taps."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from app.api import action_log

if TYPE_CHECKING:
    from app.api.session_manager import GameSession

# Window for the rapid-pair "undo correction" flow (see GameService.add_point).
RAPID_PAIR_WINDOW_S = 5.0


def consume_rapid_pair(
    session: GameSession,
    team: int,
    undo: bool,
    point_type: str | None = None,
    error_type: str | None = None,
    landing_set: int | None = None,
) -> bool:
    """Return True when the incoming add_point collapses with a recent opposite action.

    ``point_type`` / ``error_type`` are the classification tags of the
    *incoming* forward tap (``None`` on an undo). They gate the recovery
    branch: an undo→tap collapse only fires when the re-tap reproduces
    the same point, classification included — see the recovery comment
    below.
    """
    cached = session.rapid_pair_cache.get(team)
    if not cached:
        return False
    if cached.get("kind") == ("undo" if undo else "forward"):
        return False
    now = time.time()
    ts = cached.get("ts")
    if not isinstance(ts, (int, float)) or now - ts > RAPID_PAIR_WINDOW_S:
        session.rapid_pair_cache.pop(team, None)
        return False

    audit_ts = cached.get("audit_ts")
    if undo:
        # Collapse only when the undo reverses that very point: it must land
        # in the set the forward scored in. Leftover points in the next set
        # (after an earlier un-win) would otherwise take the decrement while
        # the forward's record — say, a set-winning point — disappeared.
        forward_set = cached.get("score_set")
        if landing_set is not None and forward_set is not None and forward_set != landing_set:
            session.rapid_pair_cache.pop(team, None)
            return False
        if audit_ts is not None and action_log.tombstone_ts(session.oid, audit_ts):
            session.undoable_forward_count = max(0, session.undoable_forward_count - 1)
    else:
        # Recovery: a forward tap reversing a just-applied undo. Only
        # collapse when the re-tap reproduces the *same* point — its
        # classification included. If the operator re-tags it differently
        # (e.g. undo an "ace", then re-score the rally as a "kill"), bail
        # so the new tag lands as a fresh forward record instead of
        # silently restoring the old tag.
        if (
            cached.get("popped_point_type") != point_type
            or cached.get("popped_error_type") != error_type
        ):
            session.rapid_pair_cache.pop(team, None)
            return False
        # ...and only when it lands in the set the restored record scored
        # in. An undo can fall back a set (the current one had nothing to
        # undo), so the re-tap may score in a different set; restoring the
        # old record would then make the log describe a point that is not
        # on the board.
        popped_set = cached.get("popped_score_set")
        if landing_set is not None and popped_set is not None and popped_set != landing_set:
            session.rapid_pair_cache.pop(team, None)
            return False
        tombstone_ok = audit_ts is not None and action_log.tombstone_ts(
            session.oid, audit_ts,
        )
        if tombstone_ok:
            popped_ref = cached.get("popped_ref_ts")
            if popped_ref is not None and action_log.restore_popped(
                session.oid, popped_ref,
            ):
                session.undoable_forward_count += 1

    session.rapid_pair_cache.pop(team, None)
    return True


def record_rapid_pair_seed(
    session: GameSession,
    team: int,
    undo: bool,
    audit_record: dict | None,
    popped: dict | None,
    serve_before: str | None = None,
    popped_was_newest: bool = False,
) -> None:
    """Stash the action that just landed for a possible rapid-pair collapse.

    A collapse writes no audit record of its own, so it is only sound while
    the pair is adjacent in the log: every later record's post-state
    snapshot would otherwise still include (or omit) the cancelled action,
    and the log would stop describing the board. Hence:

    * seeding one team clears the other team's entry — any audited point in
      between breaks adjacency (other mutations already clear the cache);
    * an undo is only seeded when the forward it popped was the newest
      visible record, so a quick re-tap restores it in its true position.
    """
    session.rapid_pair_cache.clear()
    if undo and not popped_was_newest:
        return
    if not isinstance(audit_record, dict):
        session.rapid_pair_cache.pop(team, None)
        return
    ts = audit_record.get("ts")
    if not isinstance(ts, (int, float)):
        session.rapid_pair_cache.pop(team, None)
        return
    entry: dict = {
        "kind": "undo" if undo else "forward",
        "ts": time.time(),
        "audit_ts": ts,
        # The serve marker before this action: a forward that a quick undo
        # cancels must leave the serve where it was, or the pair is not
        # the no-op the audit log will say it was.
        "serve_before": serve_before,
        "score_set": (audit_record.get("result") or {}).get("score_set"),
    }
    if undo and isinstance(popped, dict):
        popped_ts = popped.get("ts")
        if isinstance(popped_ts, (int, float)):
            entry["popped_ref_ts"] = popped_ts
            popped_result = popped.get("result") or {}
            entry["popped_score_set"] = popped_result.get(
                "score_set", popped_result.get("current_set"),
            )
            # Remember the original point's tags so a quick re-tap can
            # tell "same point" (collapse) from "re-classified" (record
            # the new tag instead of restoring the old one).
            popped_params = popped.get("params") or {}
            entry["popped_point_type"] = popped_params.get("point_type")
            entry["popped_error_type"] = popped_params.get("error_type")
    session.rapid_pair_cache[team] = entry


def invalidate_rapid_pair_cache(session: GameSession) -> None:
    """Clear per-team rapid-pair cache after non-add_point mutations."""
    if session.rapid_pair_cache:
        session.rapid_pair_cache.clear()
