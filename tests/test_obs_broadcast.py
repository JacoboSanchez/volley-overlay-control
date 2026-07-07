"""ObsBroadcastHub hardening — send timeout, per-overlay cap, task hygiene.

The OBS hub mirrors ``WSHub``'s protections: a wedged browser source must
not stall broadcasts to the rest, a leaked public token must not allow
unbounded fan-out, and a failing state getter must not kill the task map.
"""

import asyncio

import pytest

from app.overlay.broadcast import ObsBroadcastHub, ObsHubFull


class FakeWS:
    """Minimal stand-in for a Starlette WebSocket."""

    def __init__(self, *, hang: bool = False):
        self.hang = hang
        self.sent: list[str] = []

    async def send_text(self, message: str) -> None:
        if self.hang:
            await asyncio.sleep(3600)
        self.sent.append(message)


async def test_hung_client_is_evicted_and_others_still_receive(monkeypatch):
    monkeypatch.setattr(ObsBroadcastHub, "_BROADCAST_SEND_TIMEOUT", 0.05)
    hub = ObsBroadcastHub()
    stuck, healthy = FakeWS(hang=True), FakeWS()
    hub.add_client("ov1", stuck)
    hub.add_client("ov1", healthy)

    await hub.broadcast_now("ov1", {"score": 1})

    assert healthy.sent == ['{"score": 1}']
    # The wedged socket is treated as stale and dropped from the roster.
    assert hub.get_clients("ov1") == [healthy]

    # A second broadcast is instant (no stuck client left to wait on).
    await asyncio.wait_for(hub.broadcast_now("ov1", {"score": 2}), timeout=0.5)
    assert healthy.sent[-1] == '{"score": 2}'


async def test_client_cap_rejects_with_obs_hub_full(monkeypatch):
    monkeypatch.setattr(ObsBroadcastHub, "_MAX_CLIENTS_PER_OVERLAY", 2)
    hub = ObsBroadcastHub()
    hub.add_client("ov1", FakeWS())
    hub.add_client("ov1", FakeWS())

    with pytest.raises(ObsHubFull) as exc:
        hub.add_client("ov1", FakeWS())
    assert exc.value.cap == 2
    assert hub.get_client_count("ov1") == 2

    # Other overlays are unaffected by ov1's cap.
    hub.add_client("ov2", FakeWS())
    assert hub.get_client_count("ov2") == 1


async def test_failing_get_state_is_logged_and_reaped():
    hub = ObsBroadcastHub()
    ws = FakeWS()
    hub.add_client("ov1", ws)

    def boom():
        raise RuntimeError("state store exploded")

    hub.schedule_broadcast("ov1", boom)
    task = hub._broadcast_tasks["ov1"]
    await task  # must not raise — the exception is swallowed and logged

    # The done-callback reaps the finished task from the map.
    await asyncio.sleep(0)
    assert "ov1" not in hub._broadcast_tasks

    # Later broadcasts still work.
    hub.schedule_broadcast("ov1", lambda: {"ok": True})
    await hub._broadcast_tasks["ov1"]
    assert ws.sent == ['{"ok": true}']


async def test_superseded_broadcast_only_sends_once():
    hub = ObsBroadcastHub()
    ws = FakeWS()
    hub.add_client("ov1", ws)

    hub.schedule_broadcast("ov1", lambda: {"n": 1})
    hub.schedule_broadcast("ov1", lambda: {"n": 2})
    await asyncio.sleep(0.15)

    assert ws.sent == ['{"n": 2}']
    assert "ov1" not in hub._broadcast_tasks
