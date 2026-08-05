"""Bridge audit-log mutations onto the control WebSocket.

``action_log`` is storage and ``WSHub`` is transport; neither should import
the other. This module is the one place that knows about both, and it is
wired up once at startup by :func:`app.bootstrap.create_app`.

Why it exists: the control UI used to re-``GET /api/v1/audit`` after every
confirmed point, because a score change was the only signal it had that the
log had grown. That is roughly 150-200 extra round trips over a five-set
match, all of them racing the very ``POST`` that caused them — the race
``App`` worked around by triggering off ``confirmedState`` rather than the
optimistic state. Audit rows are now pushed down the socket the board
already holds, so the refetch only happens when the client genuinely cannot
extend its copy.

The push is an optimisation, never the source of truth. ``GET /audit``
still returns the authoritative log, and every client re-reads it on
connect, on an ``invalidate``, and whenever a version gap says it missed a
message. A dropped broadcast therefore costs one extra fetch, not a wrong
history.
"""

from __future__ import annotations

import logging

from app.api import action_log
from app.api.ws_hub import WSHub

logger = logging.getLogger(__name__)


def _on_audit_mutation(
    oid: str,
    event: str,
    version: int,
    record: dict | None,
) -> None:
    """Forward one ``action_log`` mutation to the OID's WebSocket clients.

    *oid* here is the storage key (``"<user_id>:<oid>"``), which is what
    both ``action_log`` and ``WSHub`` are keyed by — so the fan-out reaches
    exactly the clients watching this user's board and nobody else's.
    """
    WSHub.broadcast_audit_sync(oid, event, version, record)


def install() -> None:
    """Point ``action_log``'s observer at the WebSocket hub.

    Idempotent — installing twice just re-registers the same function.
    """
    action_log.set_observer(_on_audit_mutation)


def uninstall() -> None:
    """Detach the observer. Used by tests that assert on the un-bridged log."""
    action_log.set_observer(None)
