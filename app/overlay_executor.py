"""Process-wide bounded executor for ordered overlay background work.

``ThreadPoolExecutor`` deliberately uses an unbounded internal queue.  That is
convenient for general-purpose work, but it lets a burst of scoreboard actions
retain an arbitrary number of payloads in memory.  This wrapper adds two
properties the overlay path needs:

* a fixed process-wide capacity, with submitters applying backpressure once it
  is full; and
* FIFO execution for work targeting the same per-user storage key, while work
  for different overlays can still run concurrently.

The singleton is lazy and restartable so importing application modules does
not create worker threads and independent application lifespans in tests do
not inherit a shut-down pool.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import deque
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from app.env_vars_manager import EnvVarsManager
from app.metrics import (
    record_overlay_executor_run,
    record_overlay_executor_wait,
    set_overlay_executor_queue_depth,
)

logger = logging.getLogger(__name__)

_DEFAULT_MAX_WORKERS = 8
_DEFAULT_MAX_QUEUE = 256


class OverlayExecutorSaturated(RuntimeError):
    """Submission would have parked the asyncio thread on backpressure.

    Blocking until a slot frees is the intended behaviour for worker
    threads, but the same wait on the event-loop thread stalls *every*
    request and WebSocket broadcast until capacity is released. Callers
    reached from an ``async def`` handler must therefore hop to a worker
    thread first (``run_in_threadpool``), which is what every mutating
    route does.
    """


def _on_event_loop_thread() -> bool:
    """Return True when the caller runs on a thread driving an asyncio loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


@dataclass(slots=True)
class _WorkItem:
    future: Future[Any]
    function: Callable[..., Any]
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    queued_at: float


class OverlayTaskExecutor:
    """Bounded worker pool that preserves FIFO order within each key."""

    def __init__(self, max_workers: int, max_queue: int) -> None:
        if max_workers < 1:
            raise ValueError("max_workers must be at least 1")
        if max_queue < 1:
            raise ValueError("max_queue must be at least 1")
        self.max_workers = max_workers
        self.max_queue = max_queue
        self._pool = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="overlay",
        )
        # Capacity counts work that is executing as well as work waiting for a
        # worker.  ThreadPoolExecutor's own unbounded queue therefore never
        # sees more than max_workers submissions at a time: subsequent work
        # remains in the keyed deques below.
        self._capacity = threading.BoundedSemaphore(max_workers + max_queue)
        self._condition = threading.Condition()
        self._queues: dict[str, deque[_WorkItem]] = {}
        self._ready_keys: deque[str] = deque()
        self._ready_key_set: set[str] = set()
        self._running_keys: set[str] = set()
        self._running_count = 0
        self._queued_count = 0
        self._unfinished_count = 0
        self._shutdown = False

    @property
    def queue_depth(self) -> int:
        """Return work waiting behind an active task for the same key."""
        with self._condition:
            return self._queued_count

    def submit(
        self,
        key: str,
        function: Callable[..., Any],
        /,
        *args: Any,
        **kwargs: Any,
    ) -> Future[Any]:
        """Queue *function* under *key*, blocking while capacity is full.

        Raises :class:`OverlayExecutorSaturated` instead of blocking when the
        caller is on the event-loop thread and no slot is free.
        """
        # Deliberately acquire before allocating/copying the item so overload
        # cannot retain one payload per blocked caller outside the bounded
        # queue as well as those already accepted into it.
        queued_at = time.perf_counter()
        self._acquire_capacity()
        item = _WorkItem(
            future=Future(),
            function=function,
            args=args,
            kwargs=kwargs,
            queued_at=queued_at,
        )
        with self._condition:
            if self._shutdown:
                self._capacity.release()
                raise RuntimeError("cannot schedule work after executor shutdown")
            self._unfinished_count += 1
            self._queues.setdefault(key, deque()).append(item)
            self._queued_count += 1
            set_overlay_executor_queue_depth(self._queued_count)
            if key not in self._running_keys and key not in self._ready_key_set:
                self._ready_keys.append(key)
                self._ready_key_set.add(key)
            self._dispatch_ready_locked()
        return item.future

    def _acquire_capacity(self) -> None:
        """Reserve one slot, never parking a thread that drives the loop.

        Backpressure is the point of the bound, so a worker thread waits.
        The event-loop thread must not: a burst past ``max_workers +
        max_queue`` — or one slow overlay task — would otherwise freeze
        every HTTP request and WebSocket broadcast in the process until a
        slot frees.
        """
        if self._capacity.acquire(blocking=False):
            return
        if _on_event_loop_thread():
            raise OverlayExecutorSaturated(
                "overlay executor is saturated; submit from a worker thread "
                "instead of the event loop"
            )
        self._capacity.acquire()

    def _dispatch_ready_locked(self) -> None:
        """Assign ready keys to free workers while the condition is held."""
        while self._running_count < self.max_workers and self._ready_keys:
            key = self._ready_keys.popleft()
            self._ready_key_set.discard(key)
            queue = self._queues[key]
            item = queue.popleft()
            self._queued_count -= 1
            set_overlay_executor_queue_depth(self._queued_count)
            if not queue:
                del self._queues[key]
            self._running_keys.add(key)
            self._running_count += 1
            self._pool.submit(self._run_item, key, item)

    def _run_item(self, key: str, item: _WorkItem) -> None:
        started_at = time.perf_counter()
        record_overlay_executor_wait(started_at - item.queued_at)
        if item.future.set_running_or_notify_cancel():
            try:
                result = item.function(*item.args, **item.kwargs)
            except BaseException as exc:
                item.future.set_exception(exc)
                # The ordering key contains the account id and raw OID; keep
                # it out of logs even when LOG_REDACT is disabled.
                logger.exception("Overlay background task failed")
            else:
                item.future.set_result(result)
            finally:
                record_overlay_executor_run(time.perf_counter() - started_at)
        self._capacity.release()

        with self._condition:
            self._unfinished_count -= 1
            self._running_count -= 1
            self._running_keys.discard(key)
            queue = self._queues.get(key)
            if queue:
                self._ready_keys.append(key)
                self._ready_key_set.add(key)
            self._dispatch_ready_locked()
            if self._unfinished_count == 0:
                self._condition.notify_all()

    def run_after_pending(
        self,
        key: str,
        function: Callable[..., Any],
        /,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Run *function* after earlier work for *key* and wait for it.

        The cleanup itself is part of the keyed FIFO rather than happening
        after a separate ``drain`` call. New work accepted concurrently is
        therefore ordered either before or after the cleanup and can never
        slip into the drain/delete gap.

        This is a synchronous barrier for blocking lifecycle paths. Calling
        it from an asyncio event-loop thread would park that loop while prior
        overlay work finishes, so reject that misuse explicitly.
        """
        if _on_event_loop_thread():
            raise RuntimeError(
                "run_after_pending must be called from a worker thread"
            )
        return self.submit(key, function, *args, **kwargs).result()

    def shutdown(self, *, wait: bool = True, cancel_futures: bool = False) -> None:
        """Reject new work, optionally cancel queued work, and stop workers."""
        if not wait and not cancel_futures:
            raise ValueError("wait=False requires cancel_futures=True")
        cancelled: list[_WorkItem] = []
        with self._condition:
            if self._shutdown:
                return
            self._shutdown = True
            if cancel_futures:
                for queue in self._queues.values():
                    cancelled.extend(queue)
                self._queues.clear()
                self._ready_keys.clear()
                self._ready_key_set.clear()
                self._queued_count = 0
                self._unfinished_count -= len(cancelled)
                set_overlay_executor_queue_depth(0)
                for item in cancelled:
                    item.future.cancel()
                    self._capacity.release()
                if self._unfinished_count == 0:
                    self._condition.notify_all()
            if wait:
                while self._unfinished_count:
                    self._condition.wait()
        # Queued keyed work was already cancelled above. Assigned tasks must
        # still run so their public Future reaches a terminal state.
        self._pool.shutdown(wait=wait, cancel_futures=False)
        set_overlay_executor_queue_depth(0)


_singleton_lock = threading.Lock()
_singleton: OverlayTaskExecutor | None = None


def get_overlay_executor() -> OverlayTaskExecutor:
    """Return the process-wide overlay executor, creating it lazily."""
    global _singleton
    with _singleton_lock:
        if _singleton is None:
            workers = EnvVarsManager.get_int_env(
                "OVERLAY_EXECUTOR_MAX_WORKERS",
                _DEFAULT_MAX_WORKERS,
                minimum=1,
                maximum=128,
            )
            queue = EnvVarsManager.get_int_env(
                "OVERLAY_EXECUTOR_MAX_QUEUE",
                _DEFAULT_MAX_QUEUE,
                minimum=1,
                maximum=100_000,
            )
            _singleton = OverlayTaskExecutor(workers, queue)
        return _singleton


def shutdown_overlay_executor(
    *,
    wait: bool = True,
    cancel_futures: bool = False,
) -> None:
    """Shut down and detach the singleton once per application lifespan."""
    global _singleton
    with _singleton_lock:
        executor = _singleton
        _singleton = None
    if executor is not None:
        executor.shutdown(wait=wait, cancel_futures=cancel_futures)
