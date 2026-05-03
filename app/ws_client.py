"""WebSocket client for persistent communication with custom overlay servers.

Manages a background connection to the overlay server's /ws/control/{overlay_id}
endpoint, enabling low-latency state pushes and bidirectional event flow.
Falls back gracefully when the overlay server does not support WebSocket control.
"""
import json
import logging
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# Protocol version this client supports
WS_CONTROL_PROTOCOL_VERSION = 1

# Reconnection parameters
_RECONNECT_BASE = 1.0      # seconds
_RECONNECT_MAX = 30.0       # seconds
_HEARTBEAT_INTERVAL = 25.0  # seconds (inside the server's 30s timeout)
# If no inbound traffic (pong or otherwise) lands within this many seconds,
# assume the socket is a zombie and force a reconnect. Must be > 2 *
# _HEARTBEAT_INTERVAL so a single dropped pong does not churn the connection.
_ZOMBIE_DEADLINE = 55.0


class WSControlClient:
    """Persistent WebSocket connection to a custom overlay server.

    The client runs a background daemon thread that:
    - Maintains the WebSocket connection with auto-reconnect
    - Sends heartbeat pings every 25 seconds
    - Dispatches incoming messages to a callback
    - Exposes a thread-safe ``send()`` method for pushing state updates
    """

    def __init__(
        self,
        overlay_id: str,
        ws_url: str,
        on_event: Optional[Callable[[dict], None]] = None,
    ):
        self._overlay_id = overlay_id
        self._ws_url = ws_url
        self._on_event = on_event

        self._ws = None
        self._connected = False
        self._obs_client_count = 0
        self._last_inbound_ts: float = 0.0
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # -- public properties --------------------------------------------------

    @property
    def is_connected(self) -> bool:
        with self._lock:
            if not self._connected:
                return False
            last_ts = self._last_inbound_ts
        if last_ts and (time.monotonic() - last_ts > _ZOMBIE_DEADLINE):
            return False
        return True

    @property
    def obs_client_count(self) -> int:
        return self._obs_client_count

    # -- lifecycle ----------------------------------------------------------

    def connect(self) -> None:
        """Start the background connection thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="ws-control"
        )
        self._thread.start()
        logger.info(
            "WSControlClient started for overlay '%s' → %s",
            self._overlay_id, self._ws_url,
        )

    def disconnect(self) -> None:
        """Stop the background thread and close the connection."""
        self._stop_event.set()
        with self._lock:
            if self._ws:
                # close() races the receiver thread; the socket may already
                # be torn down on the remote side. Swallow.
                try:
                    self._ws.close()
                except Exception:  # nosec B110
                    pass
                self._ws = None
            self._connected = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info(
            "WSControlClient stopped for overlay '%s'", self._overlay_id
        )

    # -- sending ------------------------------------------------------------

    def send_state(self, payload: dict) -> bool:
        """Send a state_update message. Returns True on success."""
        return self._send({
            "type": "state_update",
            "payload": payload,
        })

    def send_visibility(self, show: bool) -> bool:
        """Send a visibility toggle message."""
        return self._send({
            "type": "visibility",
            "show": show,
        })

    def send_raw_config(self, payload: dict) -> bool:
        """Send a raw_config message (model and/or customization)."""
        return self._send({
            "type": "raw_config",
            "payload": payload,
        })

    def send_get_state(self) -> bool:
        """Request current state from the overlay server."""
        return self._send({"type": "get_state"})

    def _send(self, msg: dict) -> bool:
        """Thread-safe send. Returns False if not connected."""
        with self._lock:
            if not self._ws or not self._connected:
                return False
            try:
                self._ws.send(json.dumps(msg))
                return True
            except Exception as e:
                logger.debug("WS send failed: %s", e)
                self._connected = False
                return False

    # -- background loop ----------------------------------------------------

    def _run_loop(self) -> None:
        """Background thread: connect, listen, reconnect."""
        if not hasattr(self, '_ws_lib'):
            import websocket
            self._ws_lib = websocket

        backoff = _RECONNECT_BASE

        while not self._stop_event.is_set():
            try:
                logger.debug("Connecting to %s …", self._ws_url)
                sock = self._ws_lib.create_connection(
                    self._ws_url, timeout=10
                )
                with self._lock:
                    self._ws = sock
                    self._connected = True
                    self._last_inbound_ts = time.monotonic()
                backoff = _RECONNECT_BASE  # reset on success
                logger.info("WS connected to %s", self._ws_url)

                self._listen(sock)

            except Exception as e:
                logger.debug("WS connection error: %s", e)
            finally:
                with self._lock:
                    self._connected = False
                    self._ws = None

            if self._stop_event.is_set():
                break

            # Exponential backoff
            logger.debug("Reconnecting in %.1fs …", backoff)
            self._stop_event.wait(timeout=backoff)
            backoff = min(backoff * 2, _RECONNECT_MAX)

    def _listen(self, sock) -> None:
        """Read messages until disconnect or stop. Sends periodic pings."""
        sock.settimeout(_HEARTBEAT_INTERVAL)
        last_ping = time.monotonic()

        while not self._stop_event.is_set():
            try:
                raw = sock.recv()
                if raw is None:
                    break
                self._last_inbound_ts = time.monotonic()
                msg = json.loads(raw)
                self._handle_message(msg)
            except self._ws_lib.WebSocketTimeoutException:
                pass  # recv timed out — send heartbeat below
            except Exception as e:
                logger.debug("WS recv error: %s", e)
                break

            # Zombie detection: no inbound traffic for too long → force reconnect.
            now = time.monotonic()
            if now - self._last_inbound_ts > _ZOMBIE_DEADLINE:
                logger.warning(
                    "WS zombie detected on %s (%.1fs without inbound); "
                    "reconnecting.",
                    self._ws_url, now - self._last_inbound_ts,
                )
                break

            # Heartbeat
            if now - last_ping >= _HEARTBEAT_INTERVAL:
                try:
                    sock.send(json.dumps({"type": "ping"}))
                    last_ping = now
                except Exception:
                    break

    def _handle_message(self, msg: dict) -> None:
        """Dispatch an incoming message."""
        msg_type = msg.get("type")

        if msg_type == "connected":
            protocol = msg.get("protocol", 0)
            if protocol != WS_CONTROL_PROTOCOL_VERSION:
                logger.warning(
                    "Protocol mismatch: server=%d, client=%d",
                    protocol, WS_CONTROL_PROTOCOL_VERSION,
                )
            self._obs_client_count = msg.get("obs_clients", 0)
            logger.info(
                "Handshake OK — overlay '%s', OBS clients: %d",
                msg.get("overlay_id"), self._obs_client_count,
            )

        elif msg_type == "ack":
            self._obs_client_count = msg.get(
                "obs_clients", self._obs_client_count
            )
            logger.debug("Ack: %s", msg.get("ref"))

        elif msg_type == "obs_event":
            self._obs_client_count = msg.get("obs_clients", 0)
            logger.info(
                "OBS event: %s (clients: %d)",
                msg.get("event"), self._obs_client_count,
            )

        elif msg_type == "pong":
            pass  # heartbeat response

        elif msg_type == "state":
            pass  # response to get_state — handled via callback

        if self._on_event:
            try:
                self._on_event(msg)
            except Exception:
                logger.exception("Event callback error")
