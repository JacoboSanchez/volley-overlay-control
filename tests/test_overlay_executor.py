"""Ordering, capacity and lifecycle tests for the shared overlay executor."""

from __future__ import annotations

import threading
import time

from app.backend import Backend
from app.conf import Conf
from app.overlay_executor import OverlayTaskExecutor, shutdown_overlay_executor


def test_same_key_tasks_run_in_submission_order() -> None:
    executor = OverlayTaskExecutor(max_workers=3, max_queue=8)
    release_first = threading.Event()
    first_started = threading.Event()
    events: list[str] = []

    def first() -> None:
        events.append("first-start")
        first_started.set()
        assert release_first.wait(timeout=2)
        events.append("first-end")

    def record(value: str) -> None:
        events.append(value)

    first_future = executor.submit("1:scoreboard", first)
    assert first_started.wait(timeout=2)
    second_future = executor.submit("1:scoreboard", record, "second")
    third_future = executor.submit("1:scoreboard", record, "third")
    release_first.set()

    first_future.result(timeout=2)
    second_future.result(timeout=2)
    third_future.result(timeout=2)
    executor.shutdown()

    assert events == ["first-start", "first-end", "second", "third"]


def test_different_keys_can_run_concurrently() -> None:
    executor = OverlayTaskExecutor(max_workers=2, max_queue=2)
    rendezvous = threading.Barrier(2)

    def meet() -> str:
        rendezvous.wait(timeout=2)
        return "done"

    first = executor.submit("1:one", meet)
    second = executor.submit("1:two", meet)

    assert first.result(timeout=2) == "done"
    assert second.result(timeout=2) == "done"
    executor.shutdown()


def test_capacity_applies_backpressure_to_submitters() -> None:
    executor = OverlayTaskExecutor(max_workers=1, max_queue=1)
    release_first = threading.Event()
    first_started = threading.Event()
    third_attempting = threading.Event()
    third_submitted = threading.Event()

    def block() -> None:
        first_started.set()
        assert release_first.wait(timeout=2)

    first = executor.submit("same", block)
    assert first_started.wait(timeout=2)
    second = executor.submit("same", lambda: None)

    def submit_third() -> None:
        third_attempting.set()
        future = executor.submit("same", lambda: None)
        third_submitted.set()
        future.result(timeout=2)

    submitter = threading.Thread(target=submit_third)
    submitter.start()
    assert third_attempting.wait(timeout=2)
    time.sleep(0.05)
    assert not third_submitted.is_set()

    release_first.set()
    assert third_submitted.wait(timeout=2)
    first.result(timeout=2)
    second.result(timeout=2)
    submitter.join(timeout=2)
    executor.shutdown()


def test_backends_share_pool_and_session_shutdown_does_not_stop_it() -> None:
    first_conf = Conf()
    first_conf.oid = "one"
    second_conf = Conf()
    second_conf.oid = "two"
    first = Backend(first_conf)
    second = Backend(second_conf)

    assert first.executor is second.executor
    first.shutdown()

    future = second.executor.submit("two", lambda: 42)
    assert future.result(timeout=2) == 42


def test_existing_backend_reacquires_pool_after_lifespan_shutdown() -> None:
    conf = Conf()
    conf.oid = "one"
    backend = Backend(conf)
    previous = backend.executor

    shutdown_overlay_executor(wait=True, cancel_futures=True)

    replacement = backend.executor
    assert replacement is not previous
    assert replacement.submit("one", lambda: 42).result(timeout=2) == 42


def test_failed_task_does_not_block_later_work_for_same_key() -> None:
    executor = OverlayTaskExecutor(max_workers=1, max_queue=2)

    def fail() -> None:
        raise RuntimeError("expected failure")

    failed = executor.submit("same", fail)
    later = executor.submit("same", lambda: "recovered")

    try:
        failed.result(timeout=2)
    except RuntimeError as exc:
        assert str(exc) == "expected failure"
    else:  # pragma: no cover - documents the expected terminal state
        raise AssertionError("failed task unexpectedly succeeded")
    assert later.result(timeout=2) == "recovered"
    executor.shutdown()
