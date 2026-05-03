"""Thread-safe TTL cache for the most recently fetched overlay customization.

Extracted from :class:`app.backend.Backend` so the read/write/expiry policy
lives in one place and can be unit-tested without spinning up an overlay
backend or an HTTP session.

The cache is intentionally tiny (one slot per ``Backend``) because each
backend instance maps to one OID; multi-OID coordination happens at the
``GameSession`` layer above. All reads and writes deep-copy the dict so
callers can mutate their copy without poisoning the cached value, and a
lock guards the slot because background save tasks (running on the
backend's ``ThreadPoolExecutor``) update the cache concurrently with
foreground reads from request handlers.
"""

from __future__ import annotations

import threading
import time
from typing import Optional


class CustomizationCache:
    """A single-slot TTL cache for an overlay-customization dict."""

    def __init__(self, ttl_seconds: float):
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self._ttl = float(ttl_seconds)
        self._data: Optional[dict] = None
        self._timestamp: float = 0.0
        self._lock = threading.Lock()

    @property
    def ttl_seconds(self) -> float:
        return self._ttl

    def remember(self, data: Optional[dict]) -> None:
        """Store *data* as the freshest snapshot. ``None`` clears the slot.

        The dict is shallow-copied to insulate the cache from later
        mutations by the caller.
        """
        with self._lock:
            self._data = data.copy() if data is not None else None
            self._timestamp = time.monotonic()

    def fresh(self) -> Optional[dict]:
        """Return a copy of the cached dict if not stale, else ``None``."""
        with self._lock:
            if self._data is None:
                return None
            if (time.monotonic() - self._timestamp) > self._ttl:
                return None
            return self._data.copy()

    def invalidate(self) -> None:
        """Drop any cached value without waiting for TTL expiry."""
        with self._lock:
            self._data = None
            self._timestamp = 0.0
