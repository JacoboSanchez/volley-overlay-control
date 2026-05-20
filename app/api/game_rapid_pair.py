"""Rapid-pair undo correction for consecutive add_point taps."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from app.api import action_log

if TYPE_CHECKING:
    from app.api.session_manager import GameSession

# Window for the rapid-pair "undo correction" flow (see GameService.add_point).
RAPID_PAIR_WINDOW_S = 5.0


def consume_rapid_pair(session: GameSession, team: int, undo: bool) -> bool:
    """Return True when the incoming add_point collapses with a recent opposite action."""
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
    session.rapid_pair_cache[team] = entry


def invalidate_rapid_pair_cache(session: GameSession) -> None:
    """Clear per-team rapid-pair cache after non-add_point mutations."""
    if session.rapid_pair_cache:
        session.rapid_pair_cache.clear()
