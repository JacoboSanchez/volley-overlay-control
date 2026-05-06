import asyncio
import json
import logging

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WSHub:
    """Manages WebSocket connections from frontend clients and broadcasts
    game-state updates to all of them.

    Connections are grouped by OID so that clients only receive updates for
    the session they are subscribed to.
    """

    # {oid: set[WebSocket]}
    _connections: dict = {}

    @classmethod
    async def connect(cls, ws: WebSocket, oid: str):
        await ws.accept()
        cls._connections.setdefault(oid, set()).add(ws)
        logger.info(
            "WS client connected for OID=%s (total=%d)",
            oid, len(cls._connections[oid]))

    @classmethod
    def disconnect(cls, ws: WebSocket, oid: str):
        conns = cls._connections.get(oid)
        if conns:
            conns.discard(ws)
            if not conns:
                del cls._connections[oid]
        logger.info("WS client disconnected for OID=%s", oid)

    # Per-socket send timeout. A slow/hung client must not stall broadcasts
    # to the rest of the subscribers (nor the main state-update path).
    _BROADCAST_SEND_TIMEOUT = 2.0

    @classmethod
    async def _broadcast_text(cls, oid: str, message: str):
        """Send the pre-serialized *message* to every client for *oid*.

        Sends run concurrently with a per-socket timeout so a single stuck
        client cannot delay updates to the rest or leak memory by keeping
        a dead socket in the registry.
        """
        conns = cls._connections.get(oid)
        if not conns:
            return

        targets = list(conns)

        async def _send(ws):
            try:
                await asyncio.wait_for(
                    ws.send_text(message),
                    timeout=cls._BROADCAST_SEND_TIMEOUT,
                )
                return None
            except Exception:
                return ws

        results = await asyncio.gather(
            *(_send(ws) for ws in targets),
            return_exceptions=False,
        )

        for ws in results:
            if ws is not None:
                conns.discard(ws)
        # Only drop the OID entry if the registry still holds *our* set.
        # A concurrent ``disconnect`` could have removed it and a concurrent
        # ``connect`` could have installed a new set in the meantime; popping
        # in that case would silently lose the new client.
        if not conns and cls._connections.get(oid) is conns:
            cls._connections.pop(oid, None)

    @classmethod
    async def broadcast(cls, oid: str, data: dict):
        """Send a JSON ``state_update`` message to every client for *oid*."""
        message = json.dumps({"type": "state_update", "data": data})
        await cls._broadcast_text(oid, message)

    @classmethod
    async def broadcast_payload_json(cls, oid: str, payload_json: str):
        """Variant of :meth:`broadcast` that accepts the ``data`` field
        already serialized to JSON. Wraps it in the standard
        ``{"type":"state_update","data":<payload>}`` envelope and sends.

        Use this from the hot path (a game action) where the payload was
        produced by ``GameStateResponse.model_dump_json`` — avoids the
        round-trip ``model_dump`` → dict → ``json.dumps`` that
        :meth:`broadcast` would otherwise perform.
        """
        message = '{"type":"state_update","data":' + payload_json + '}'
        await cls._broadcast_text(oid, message)

    @classmethod
    def broadcast_sync(cls, oid: str, data: dict):
        """Fire-and-forget broadcast usable from synchronous code.

        Schedules the async broadcast on the running event loop. If there is
        no running loop (e.g. during tests) the call is silently skipped.
        """
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(cls.broadcast(oid, data))
        except RuntimeError:
            logger.debug("No running event loop — skipping broadcast for OID=%s", oid)

    @classmethod
    def broadcast_payload_json_sync(cls, oid: str, payload_json: str):
        """Sync wrapper around :meth:`broadcast_payload_json` for use from
        synchronous code paths (the ``GameService`` action methods)."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(cls.broadcast_payload_json(oid, payload_json))
        except RuntimeError:
            logger.debug("No running event loop — skipping broadcast for OID=%s", oid)

    @classmethod
    def clear(cls):
        """Remove all connections (for testing)."""
        cls._connections.clear()
