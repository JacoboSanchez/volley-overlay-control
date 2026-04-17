"""OBS WebSocket broadcast hub — debounced state pushes to browser sources.

Manages WebSocket connections from OBS browser sources and broadcasts
overlay state updates with 50ms debouncing to coalesce rapid changes.
"""

import asyncio
import json
import logging
from typing import Dict, List

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ObsBroadcastHub:
    """Tracks OBS browser source WebSocket connections and broadcasts state."""

    def __init__(self):
        self._clients: Dict[str, List[WebSocket]] = {}
        self._broadcast_tasks: Dict[str, asyncio.Task] = {}

    def add_client(self, overlay_id: str, ws: WebSocket) -> None:
        """Register an OBS browser source connection."""
        self._clients.setdefault(overlay_id, []).append(ws)

    def remove_client(self, overlay_id: str, ws: WebSocket) -> None:
        """Unregister an OBS browser source connection."""
        clients = self._clients.get(overlay_id)
        if clients and ws in clients:
            clients.remove(ws)

    def get_client_count(self, overlay_id: str) -> int:
        """Return the number of connected OBS sources for *overlay_id*."""
        return len(self._clients.get(overlay_id, []))

    def get_clients(self, overlay_id: str) -> List[WebSocket]:
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
        self._broadcast_tasks[overlay_id] = asyncio.create_task(
            self._debounced_broadcast(overlay_id, get_state)
        )

    def schedule_broadcast_from_sync(self, overlay_id: str, get_state) -> None:
        """Schedule a broadcast from a synchronous context."""
        try:
            loop = asyncio.get_running_loop()
            existing = self._broadcast_tasks.get(overlay_id)
            if existing and not existing.done():
                existing.cancel()
            self._broadcast_tasks[overlay_id] = loop.create_task(
                self._debounced_broadcast(overlay_id, get_state)
            )
        except RuntimeError:
            # No running event loop — skip broadcast (happens in tests
            # or purely synchronous code paths).
            pass

    async def _debounced_broadcast(
        self, overlay_id: str, get_state, delay: float = 0.05
    ) -> None:
        """Wait *delay* seconds then broadcast the current state."""
        try:
            await asyncio.sleep(delay)
            clients = self._clients.get(overlay_id, [])
            if not clients:
                return
            state = get_state()
            message = json.dumps(state)
            disconnected = []
            for client in clients:
                try:
                    await client.send_text(message)
                except Exception:
                    disconnected.append(client)
            for c in disconnected:
                if c in clients:
                    clients.remove(c)
            if disconnected:
                logger.debug(
                    "Cleaned up %d stale client(s) for overlay '%s'",
                    len(disconnected), overlay_id,
                )
        except asyncio.CancelledError:
            pass  # Superseded by a newer update

    async def broadcast_now(self, overlay_id: str, state: dict) -> None:
        """Immediately broadcast *state* to all clients (no debounce)."""
        clients = self._clients.get(overlay_id, [])
        if not clients:
            return
        message = json.dumps(state)
        disconnected = []
        for client in clients:
            try:
                await client.send_text(message)
            except Exception:
                disconnected.append(client)
        for c in disconnected:
            if c in clients:
                clients.remove(c)

    # -- Cleanup -----------------------------------------------------------

    async def cleanup_overlay(self, overlay_id: str) -> None:
        """Cancel pending tasks and close all clients for *overlay_id*."""
        task = self._broadcast_tasks.pop(overlay_id, None)
        if task and not task.done():
            task.cancel()
        clients = self._clients.pop(overlay_id, [])
        for client in clients:
            try:
                await client.close()
            except Exception:
                pass
