"""OBS WebSocket broadcast hub.

Manages WebSocket connections from OBS browser sources and broadcasts
overlay state updates to them with 50ms debouncing.
"""

import asyncio
import json
import logging
from typing import Dict, List

from fastapi import WebSocket

logger = logging.getLogger("ObsBroadcastHub")


class ObsBroadcastHub:
    """Manages OBS browser source WebSocket connections and state broadcasts."""

    def __init__(self):
        # {overlay_id: list[WebSocket]}
        self._clients: Dict[str, List[WebSocket]] = {}
        # {overlay_id: asyncio.Task} for debounced broadcasts
        self._broadcast_tasks: Dict[str, asyncio.Task] = {}

    def add_client(self, overlay_id: str, ws: WebSocket) -> None:
        self._clients.setdefault(overlay_id, []).append(ws)
        logger.info(
            "OBS client connected for overlay '%s' (total: %d)",
            overlay_id, len(self._clients[overlay_id]),
        )

    def remove_client(self, overlay_id: str, ws: WebSocket) -> None:
        clients = self._clients.get(overlay_id)
        if clients and ws in clients:
            clients.remove(ws)
            if not clients:
                del self._clients[overlay_id]
        logger.info("OBS client disconnected for overlay '%s'", overlay_id)

    def get_client_count(self, overlay_id: str) -> int:
        return len(self._clients.get(overlay_id, []))

    def get_clients(self, overlay_id: str) -> List[WebSocket]:
        return list(self._clients.get(overlay_id, []))

    def schedule_broadcast(self, overlay_id: str, get_state) -> None:
        """Cancel any pending broadcast and schedule a new debounced one.

        *get_state* is a callable returning the current state dict.
        """
        existing = self._broadcast_tasks.get(overlay_id)
        if existing and not existing.done():
            existing.cancel()
        self._broadcast_tasks[overlay_id] = asyncio.create_task(
            self._debounced_broadcast(overlay_id, get_state)
        )

    def schedule_broadcast_from_sync(self, overlay_id: str, get_state) -> None:
        """Fire-and-forget broadcast scheduling from synchronous code."""
        try:
            loop = asyncio.get_running_loop()
            existing = self._broadcast_tasks.get(overlay_id)
            if existing and not existing.done():
                existing.cancel()
            self._broadcast_tasks[overlay_id] = loop.create_task(
                self._debounced_broadcast(overlay_id, get_state)
            )
        except RuntimeError:
            logger.debug(
                "No running event loop — skipping broadcast for overlay '%s'",
                overlay_id,
            )

    async def _debounced_broadcast(self, overlay_id: str, get_state, delay: float = 0.05) -> None:
        """Wait *delay* seconds then broadcast state to all OBS clients."""
        try:
            await asyncio.sleep(delay)
            state = get_state()
            if state is None:
                return
            message = json.dumps(state)
            clients = self._clients.get(overlay_id, [])
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
                    "Cleaned up %d stale OBS client(s) for overlay '%s'",
                    len(disconnected), overlay_id,
                )
        except asyncio.CancelledError:
            pass

    async def broadcast_now(self, overlay_id: str, state: dict) -> None:
        """Immediately broadcast state to all OBS clients (no debounce)."""
        message = json.dumps(state)
        clients = self._clients.get(overlay_id, [])
        disconnected = []
        for client in clients:
            try:
                await client.send_text(message)
            except Exception:
                disconnected.append(client)
        for c in disconnected:
            if c in clients:
                clients.remove(c)

    def cleanup_overlay(self, overlay_id: str) -> None:
        """Cancel pending broadcasts and remove client tracking for an overlay."""
        task = self._broadcast_tasks.pop(overlay_id, None)
        if task and not task.done():
            task.cancel()
        self._clients.pop(overlay_id, None)
