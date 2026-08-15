"""Coordinate overlay creation, initialisation, and durable deletion.

Database transactions, request-scoped session work and keyed executor work end
at different times. A delete therefore needs an in-process claim that starts
before its row is removed and remains active until stale queued work has
drained and persisted runtime files are gone. Create/init and active session
requests take a shared-use claim for their whole lifetime and fail fast while
deletion owns the key.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.db.engine import after_commit, after_rollback
from app.service_errors import ConflictServiceError


class OverlayLifecycleBusy(ConflictServiceError):
    """The requested OID is being created, initialised, or deleted."""


@dataclass(slots=True)
class _LifecycleState:
    users: int = 0
    deleting: bool = False


class OverlayLifecycleLease:
    """One idempotently releasable lifecycle claim."""

    def __init__(self, gate: OverlayLifecycleGate, skey: str, *, deletion: bool) -> None:
        self._gate = gate
        self.skey = skey
        self.deletion = deletion
        self._released = False
        self._release_lock = threading.Lock()

    def release(self) -> None:
        with self._release_lock:
            if self._released:
                return
            self._released = True
        self._gate._release(self.skey, deletion=self.deletion)


class OverlayLifecycleGate:
    """Fail-fast shared-use/exclusive-delete claims keyed by storage key.

    Claims never wait. Waiting from a request that already owns a database
    transaction could deadlock SQLite against the transaction whose claim it
    is waiting for. A 409 lets the caller retry once the short lifecycle
    transition completes.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._states: dict[str, _LifecycleState] = {}

    def begin_use(self, skey: str) -> OverlayLifecycleLease:
        with self._lock:
            state = self._states.setdefault(skey, _LifecycleState())
            if state.deleting:
                raise OverlayLifecycleBusy(
                    "This overlay is being deleted; retry after cleanup completes."
                )
            state.users += 1
        return OverlayLifecycleLease(self, skey, deletion=False)

    def begin_delete(self, skey: str) -> OverlayLifecycleLease:
        with self._lock:
            state = self._states.setdefault(skey, _LifecycleState())
            if state.deleting or state.users:
                raise OverlayLifecycleBusy(
                    "This overlay is busy; retry deletion after active requests complete."
                )
            state.deleting = True
        return OverlayLifecycleLease(self, skey, deletion=True)

    def is_deleting(self, skey: str) -> bool:
        """Return whether *skey* currently has an exclusive deletion claim."""
        with self._lock:
            state = self._states.get(skey)
            return bool(state and state.deleting)

    def _release(self, skey: str, *, deletion: bool) -> None:
        with self._lock:
            state = self._states.get(skey)
            if state is None:  # pragma: no cover - defensive idempotency
                return
            if deletion:
                state.deleting = False
            else:
                state.users -= 1
            if not state.deleting and state.users == 0:
                self._states.pop(skey, None)


overlay_lifecycle_gate = OverlayLifecycleGate()


def release_after_transaction(
    db: Session,
    lease: OverlayLifecycleLease,
) -> None:
    """Keep *lease* until the request transaction commits or rolls back."""
    after_commit(db, lease.release)
    after_rollback(db, lease.release)
