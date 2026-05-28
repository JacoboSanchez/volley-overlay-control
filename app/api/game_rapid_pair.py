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
) -> None:
    """Stash the action that just landed for a possible rapid-pair collapse."""
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
    }
    if undo and isinstance(popped, dict):
        popped_ts = popped.get("ts")
        if isinstance(popped_ts, (int, float)):
            entry["popped_ref_ts"] = popped_ts
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
