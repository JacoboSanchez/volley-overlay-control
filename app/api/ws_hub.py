import asyncio
import json
import logging
import time

from fastapi import WebSocket

from app.constants import (
    WS_BROADCAST_SEND_TIMEOUT_SECONDS,
    WSHUB_CLIENT_TIMEOUT_SECONDS,
    WSHUB_HEARTBEAT_INTERVAL_SECONDS,
    WSHUB_MAX_CLIENTS_PER_OID,
)
from app.metrics import set_ws_gauges

logger = logging.getLogger(__name__)


class WSHubFull(Exception):
    """Raised by :meth:`WSHub.connect` when an OID is at its connection cap.

    The endpoint catches this and closes the upgrade with WebSocket
    code 1013 ("Try Again Later"), which is the conventional
    server-side back-pressure signal. The OID is preserved on the
    exception so the caller can include it in the close reason for
    log correlation.
    """

    def __init__(self, oid: str, cap: int):
        super().__init__(
            f"OID {oid!r} is at the {cap}-client cap.")
        self.oid = oid
        self.cap = cap


class WSHub:
    """Manages WebSocket connections from frontend clients and broadcasts
    game-state updates to all of them.

    Connections are grouped by OID so that clients only receive updates for
    the session they are subscribed to.
    """

    # {oid: set[WebSocket]}
    _connections: dict = {}
    # Strong references to in-flight fire-and-forget broadcast tasks. Without
    # this, the asyncio event loop may garbage-collect a task created via
    # ``loop.create_task(...)`` before it finishes, dropping the broadcast.
    _pending_tasks: set = set()
    # {WebSocket: monotonic timestamp of last client activity}. Populated
    # by ``connect`` and bumped by the endpoint on every received frame
    # so the heartbeat loop can tell zombies from healthy idle clients.
    _last_seen: dict = {}
    # Background heartbeat task (created by ``start_heartbeat``).
    _heartbeat_task = None

    # Runtime-tunable copy of the cap so tests can ``monkeypatch.setattr``
    # without reaching into ``app.constants``.
    _MAX_CLIENTS_PER_OID = WSHUB_MAX_CLIENTS_PER_OID

    @classmethod
    async def connect(cls, ws: WebSocket, oid: str, *,
                      subprotocol: str | None = None):
        """Accept *ws* and register it under *oid*.

        Raises :class:`WSHubFull` (without ``accept``-ing) when the OID
        already has ``_MAX_CLIENTS_PER_OID`` subscribers. The caller is
        expected to ``await ws.close(code=1013, reason=...)`` after
        catching the exception.

        ``subprotocol`` is echoed back to the client during the
        WebSocket handshake. The Bearer-token-as-subprotocol pattern
        (RFC 6455 §4.1) requires the server to confirm the chosen
        subprotocol, otherwise the browser drops the connection
        with a protocol-mismatch error. Callers that authenticated
        via subprotocol must pass the same value here.
        """
        existing = len(cls._connections.get(oid, ()))
        if existing >= cls._MAX_CLIENTS_PER_OID:
            logger.warning(
                "Rejecting WS connect for OID=%s: %d/%d clients (cap reached)",
                oid, existing, cls._MAX_CLIENTS_PER_OID,
            )
            raise WSHubFull(oid, cls._MAX_CLIENTS_PER_OID)
        if subprotocol is not None:
            await ws.accept(subprotocol=subprotocol)
        else:
            await ws.accept()
        cls._connections.setdefault(oid, set()).add(ws)
        cls._last_seen[ws] = time.monotonic()
        cls._refresh_gauges()
        logger.info(
            "WS client connected for OID=%s (total=%d)",
            oid, len(cls._connections[oid]))

    @classmethod
    def mark_active(cls, ws: WebSocket) -> None:
        """Record that *ws* sent or received traffic just now.

        Called from the endpoint on every successful ``receive_text`` so
        the heartbeat loop can distinguish a zombie (no traffic for
        ``WSHUB_CLIENT_TIMEOUT_SECONDS``) from an idle-but-healthy tab.
        """
        if ws in cls._last_seen:
            cls._last_seen[ws] = time.monotonic()

    @classmethod
    def _refresh_gauges(cls) -> None:
        """Publish the current ``_connections`` snapshot to the Prometheus gauges.

        Cheap (one ``sum`` over a small dict). Centralises the metric
        update so the cardinality story stays in one place — neither
        gauge takes per-OID labels by design.
        """
        total = sum(len(s) for s in cls._connections.values())
        set_ws_gauges(total, len(cls._connections))

    @classmethod
    def disconnect(cls, ws: WebSocket, oid: str):
        conns = cls._connections.get(oid)
        if conns:
            conns.discard(ws)
            if not conns:
                del cls._connections[oid]
        cls._last_seen.pop(ws, None)
        cls._refresh_gauges()
        logger.info("WS client disconnected for OID=%s", oid)

    # Per-socket send timeout. A slow/hung client must not stall broadcasts
    # to the rest of the subscribers (nor the main state-update path).
    # Configure via ``WS_BROADCAST_SEND_TIMEOUT_SECONDS``.
    _BROADCAST_SEND_TIMEOUT = WS_BROADCAST_SEND_TIMEOUT_SECONDS

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

        evicted_any = False
        for ws in results:
            if ws is not None:
                conns.discard(ws)
                cls._last_seen.pop(ws, None)
                evicted_any = True
        # Only drop the OID entry if the registry still holds *our* set.
        # A concurrent ``disconnect`` could have removed it and a concurrent
        # ``connect`` could have installed a new set in the meantime; popping
        # in that case would silently lose the new client.
        if not conns and cls._connections.get(oid) is conns:
            cls._connections.pop(oid, None)
            evicted_any = True
        if evicted_any:
            cls._refresh_gauges()

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
            task = loop.create_task(cls.broadcast(oid, data))
            cls._pending_tasks.add(task)
            task.add_done_callback(cls._pending_tasks.discard)
        except RuntimeError:
            logger.debug("No running event loop — skipping broadcast for OID=%s", oid)

    @classmethod
    def broadcast_payload_json_sync(cls, oid: str, payload_json: str):
        """Sync wrapper around :meth:`broadcast_payload_json` for use from
        synchronous code paths (the ``GameService`` action methods)."""
        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(cls.broadcast_payload_json(oid, payload_json))
            cls._pending_tasks.add(task)
            task.add_done_callback(cls._pending_tasks.discard)
        except RuntimeError:
            logger.debug("No running event loop — skipping broadcast for OID=%s", oid)

    @classmethod
    def clear(cls):
        """Remove all connections (for testing)."""
        cls._connections.clear()
        cls._last_seen.clear()
        cls._refresh_gauges()

    # ----- Heartbeat (opt-in via WSHUB_HEARTBEAT_INTERVAL_SECONDS > 0) ---

    @classmethod
    async def _heartbeat_tick(cls) -> None:
        """One pass: ping every client and evict the stale ones.

        Stale = no inbound traffic recorded for more than
        ``WSHUB_CLIENT_TIMEOUT_SECONDS``. Eviction sends an explicit
        close so the client receives a proper handshake termination
        instead of a TCP reset; the disconnect bookkeeping then runs
        from the endpoint's ``finally`` clause when ``receive_text``
        raises.

        Errors per-client are caught individually so one stuck socket
        cannot wedge the whole heartbeat sweep.
        """
        now = time.monotonic()
        # Snapshot to avoid mutating the registry mid-iteration.
        targets: list[tuple[str, WebSocket]] = []
        for oid, conns in list(cls._connections.items()):
            for ws in list(conns):
                targets.append((oid, ws))
        if not targets:
            return
        ping_msg = '{"type":"ping"}'
        for oid, ws in targets:
            last_seen = cls._last_seen.get(ws, now)
            if (now - last_seen) > WSHUB_CLIENT_TIMEOUT_SECONDS:
                logger.info(
                    "Evicting WS zombie for OID=%s (idle %.0fs)",
                    oid, now - last_seen,
                )
                try:
                    await ws.close(
                        code=1011, reason="heartbeat timeout")
                except Exception:  # nosec B110 — best-effort close
                    pass
                cls.disconnect(ws, oid)
                continue
            try:
                await asyncio.wait_for(
                    ws.send_text(ping_msg),
                    timeout=cls._BROADCAST_SEND_TIMEOUT,
                )
            except Exception:
                # The send raised — treat as the same evict path so we
                # do not keep retrying a doomed socket. The client may
                # already be gone; just log at debug.
                logger.debug(
                    "Heartbeat send failed for OID=%s; evicting", oid)
                try:
                    await ws.close(code=1011, reason="ping failed")
                except Exception:  # nosec B110
                    pass
                cls.disconnect(ws, oid)

    @classmethod
    async def _heartbeat_loop(cls, interval: float) -> None:
        try:
            while True:
                await asyncio.sleep(interval)
                await cls._heartbeat_tick()
        except asyncio.CancelledError:
            raise

    @classmethod
    def start_heartbeat(cls, interval: float | None = None) -> None:
        """Schedule the heartbeat loop on the running event loop.

        No-op when *interval* (or the configured default) is 0 — the
        operator has explicitly disabled the feature, which matches the
        out-of-the-box default. Idempotent: a second call replaces the
        previous task.
        """
        effective = (
            interval if interval is not None
            else WSHUB_HEARTBEAT_INTERVAL_SECONDS
        )
        if effective <= 0:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.debug("No running loop — heartbeat not started")
            return
        cls.stop_heartbeat()
        cls._heartbeat_task = loop.create_task(
            cls._heartbeat_loop(effective))
        logger.info(
            "WS heartbeat started (every %.1fs, timeout %.1fs)",
            effective, WSHUB_CLIENT_TIMEOUT_SECONDS,
        )

    @classmethod
    def stop_heartbeat(cls) -> None:
        """Cancel the heartbeat task if one is running. Idempotent."""
        task = cls._heartbeat_task
        if task is None:
            return
        cls._heartbeat_task = None
        if not task.done():
            task.cancel()
