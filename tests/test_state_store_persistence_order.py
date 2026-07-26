"""Regression tests for per-overlay snapshot persistence ordering."""

import asyncio
import threading

import pytest

# Keep the established import order used by the state-store test modules.
from app.api import action_log  # noqa: F401
from app.overlay.state_store import OverlayStateStore


@pytest.fixture
def store(tmp_path):
    return OverlayStateStore(
        data_dir=str(tmp_path / "data"),
        templates_dir=str(tmp_path / "tpl"),
    )


@pytest.mark.asyncio
async def test_concurrent_async_updates_cannot_persist_an_older_snapshot(
    store,
    monkeypatch,
):
    """A delayed first write must not overwrite a later async update."""
    oid = "async-order"
    assert store.create_overlay(oid) is True

    real_write = store._write_state_sync
    first_write_started = threading.Event()
    second_write_finished = threading.Event()

    def delayed_write(path, state):
        points = state["team_home"]["points"]
        if points == 1:
            first_write_started.set()
            second_write_finished.wait(timeout=0.5)
        real_write(path, state)
        if points == 2:
            second_write_finished.set()

    monkeypatch.setattr(store, "_write_state_sync", delayed_write)

    first = asyncio.create_task(
        store.update_state(
            oid,
            {"team_home": {"points": 1}},
        )
    )
    assert await asyncio.to_thread(first_write_started.wait, 2)
    second = asyncio.create_task(
        store.update_state(
            oid,
            {"team_home": {"points": 2}},
        )
    )
    await asyncio.gather(first, second)

    persisted = store.load_persisted_state(oid)
    assert persisted["team_home"]["points"] == 2
    assert store.get_state(oid)["team_home"]["points"] == 2


def test_sync_update_and_visibility_write_in_mutation_order(store, monkeypatch):
    """Visibility cannot reach disk and then be replaced by an older snapshot."""
    oid = "sync-order"
    assert store.create_overlay(oid) is True

    real_write = store._write_state_sync
    first_write_started = threading.Event()
    visibility_write_finished = threading.Event()

    def delayed_write(path, state):
        visible = state["overlay_control"]["show_main_scoreboard"]
        if visible:
            first_write_started.set()
            visibility_write_finished.wait(timeout=0.5)
        real_write(path, state)
        if not visible:
            visibility_write_finished.set()

    monkeypatch.setattr(store, "_write_state_sync", delayed_write)

    first = threading.Thread(
        target=store.update_state_sync,
        args=(oid, {"team_home": {"points": 1}}),
    )
    first.start()
    assert first_write_started.wait(timeout=2)

    second = threading.Thread(target=store.set_visibility, args=(oid, False))
    second.start()
    first.join(timeout=3)
    second.join(timeout=3)

    assert not first.is_alive()
    assert not second.is_alive()
    persisted = store.load_persisted_state(oid)
    assert persisted["team_home"]["points"] == 1
    assert persisted["overlay_control"]["show_main_scoreboard"] is False
    state = store.get_state(oid)
    assert state["overlay_control"]["show_main_scoreboard"] is False
