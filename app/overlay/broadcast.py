"""OBS WebSocket broadcast hub — debounced state pushes to browser sources.

Manages WebSocket connections from OBS browser sources and broadcasts
overlay state updates with 50ms debouncing to coalesce rapid changes.
"""

import asyncio
import functools
import json
import logging

from fastapi import WebSocket

from app.constants import (
    OBS_MAX_CLIENTS_PER_OVERLAY,
    WS_BROADCAST_SEND_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)


class ObsHubFull(Exception):
    """Raised by :meth:`ObsBroadcastHub.add_client` at the per-overlay cap.

    Mirrors ``WSHubFull``: the endpoint catches this and closes the
    upgrade with WebSocket code 1013 ("Try Again Later").
    """

    def __init__(self, overlay_id: str, cap: int):
        super().__init__(
            f"overlay '{overlay_id}' is at its client cap ({cap})"
        )
        self.overlay_id = overlay_id
        self.cap = cap


class ObsBroadcastHub:
    """Tracks OBS browser source WebSocket connections and broadcasts state."""

    # Runtime-tunable copies so tests can ``monkeypatch.setattr`` without
    # reaching into ``app.constants`` (same pattern as ``WSHub``).
    _BROADCAST_SEND_TIMEOUT = WS_BROADCAST_SEND_TIMEOUT_SECONDS
    _MAX_CLIENTS_PER_OVERLAY = OBS_MAX_CLIENTS_PER_OVERLAY

    def __init__(self):
        self._clients: dict[str, list[WebSocket]] = {}
        self._broadcast_tasks: dict[str, asyncio.Task] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    def capture_event_loop(self) -> None:
        """Capture the running event loop for use from background threads."""
        self._loop = asyncio.get_running_loop()

    def add_client(self, overlay_id: str, ws: WebSocket) -> None:
        """Register an OBS browser source connection.

        Raises :class:`ObsHubFull` when the overlay already has
        ``_MAX_CLIENTS_PER_OVERLAY`` connections — call before
        ``accept``-ing so the refusal is a clean 1013 close.
        """
        clients = self._clients.setdefault(overlay_id, [])
        if len(clients) >= self._MAX_CLIENTS_PER_OVERLAY:
            logger.warning(
                "Rejecting OBS WS connect for overlay '%s': %d/%d clients (cap reached)",
                overlay_id, len(clients), self._MAX_CLIENTS_PER_OVERLAY,
            )
            raise ObsHubFull(overlay_id, self._MAX_CLIENTS_PER_OVERLAY)
        clients.append(ws)

    def remove_client(self, overlay_id: str, ws: WebSocket) -> None:
        """Unregister an OBS browser source connection."""
        clients = self._clients.get(overlay_id)
        if clients and ws in clients:
            clients.remove(ws)

    def get_client_count(self, overlay_id: str) -> int:
        """Return the number of connected OBS sources for *overlay_id*."""
        return len(self._clients.get(overlay_id, []))

    def get_clients(self, overlay_id: str) -> list[WebSocket]:
        """Return the list of connected WebSockets for *overlay_id*."""
        return list(self._clients.get(overlay_id, []))

    # -- Broadcasting ------------------------------------------------------

    def schedule_broadcast(self, overlay_id: str, get_state) -> None:
        """Cancel any pending broadcast and schedule a new 50ms debounced one.

        *get_state* is a callable returning the current state dict.
        Must be called from an async context.
        """
        existing = self._broadcast_tasks.get(overlay_id)
        if existing and not existing.done():
            existing.cancel()
        task = asyncio.create_task(
            self._debounced_broadcast(overlay_id, get_state)
        )
        self._broadcast_tasks[overlay_id] = task
        task.add_done_callback(functools.partial(self._reap_task, overlay_id))

    def _reap_task(self, overlay_id: str, task: asyncio.Task) -> None:
        """Drop the task-map entry once its task finishes (if still current)."""
        if self._broadcast_tasks.get(overlay_id) is task:
            del self._broadcast_tasks[overlay_id]

    def schedule_broadcast_from_sync(self, overlay_id: str, get_state) -> None:
        """Schedule a broadcast from a synchronous context (e.g. ThreadPoolExecutor)."""
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        loop.call_soon_threadsafe(self.schedule_broadcast, overlay_id, get_state)

    async def _send_to_clients(self, overlay_id: str, message: str) -> None:
        """Send *message* to all clients in parallel, cleaning up stale ones."""
        clients = self._clients.get(overlay_id, [])
        if not clients:
            return

        async def _send(client):
            try:
                # A slow or wedged client (TCP backpressure from a stuck
                # OBS source) must not stall delivery to the rest — treat
                # a send that exceeds the timeout as a stale client.
                await asyncio.wait_for(
                    client.send_text(message),
                    timeout=self._BROADCAST_SEND_TIMEOUT,
                )
                return None
            except Exception as exc:
                # WebSocket frameworks raise a range of exceptions on a
                # disconnected client (WebSocketDisconnect, RuntimeError,
                # ConnectionClosed depending on stack); catch broadly so
                # one stale client doesn't kill the broadcast, but log so
                # we can tell drops apart from "no clients".
                logger.debug(
                    "Dropping stale client for overlay '%s': %s",
                    overlay_id, exc,
                )
                return client

        results = await asyncio.gather(*(_send(c) for c in clients))
        disconnected = [c for c in results if c is not None]
        for c in disconnected:
            if c in clients:
                clients.remove(c)
        if disconnected:
            logger.debug(
                "Cleaned up %d stale client(s) for overlay '%s'",
                len(disconnected), overlay_id,
            )

    async def _debounced_broadcast(
        self, overlay_id: str, get_state, delay: float = 0.05
    ) -> None:
        """Wait *delay* seconds then broadcast the current state."""
        try:
            await asyncio.sleep(delay)
            state = get_state()
            message = json.dumps(state)
            await self._send_to_clients(overlay_id, message)
        except asyncio.CancelledError:
            pass  # Superseded by a newer update
        except Exception:
            # A failing get_state()/serialization must not die as an
            # unretrieved task exception — later broadcasts still work.
            logger.exception(
                "Broadcast for overlay '%s' failed", overlay_id,
            )

    async def broadcast_now(self, overlay_id: str, state: dict) -> None:
        """Immediately broadcast *state* to all clients (no debounce)."""
        message = json.dumps(state)
        await self._send_to_clients(overlay_id, message)

    # -- Cleanup -----------------------------------------------------------

    async def cleanup_overlay(self, overlay_id: str) -> None:
        """Cancel pending tasks and close all clients for *overlay_id*."""
        task = self._broadcast_tasks.pop(overlay_id, None)
        if task and not task.done():
            task.cancel()
        clients = self._clients.pop(overlay_id, [])
        for client in clients:
            # Best-effort: a client that already disconnected raises here.
            try:
                await client.close()
            except Exception:  # nosec B110
                pass
