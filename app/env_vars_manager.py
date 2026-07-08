import json
import logging
import os
import threading
import time

import requests

from app.logging_utils import redact_url

logger = logging.getLogger(__name__)

_TRUTHY_VALUES = ("1", "true", "t", "yes", "on")


def is_truthy(value: object) -> bool:
    """Return True when *value* parses as a truthy boolean string."""
    return isinstance(value, str) and value.strip().lower() in _TRUTHY_VALUES


class EnvVarsManager:
    _remote_config_cache: dict[str, str] = {}
    _cache_timestamp: float = 0
    _CACHE_EXPIRATION_SECONDS = 10
    # Serialises the refetch so concurrent callers (request pool + webhook
    # executor) don't each fire a duplicate HTTP fetch and race on the cache.
    _lock = threading.Lock()
    # True while a background revalidation thread is running.
    _refresh_in_flight = False

    @classmethod
    def get_env_var(cls, key, default=None):
        cls._load_remote_config_if_needed()
        return cls._remote_config_cache.get(key, os.environ.get(key, default))

    @classmethod
    def get_bool_env(cls, key: str, default: bool = False) -> bool:
        """Return *key* parsed as a truthy string. Unset env falls back to *default*."""
        raw = cls.get_env_var(key, None)
        if raw is None:
            return default
        return is_truthy(raw if isinstance(raw, str) else str(raw))

    @classmethod
    def _load_remote_config_if_needed(cls):
        remote_config_url = os.environ.get('REMOTE_CONFIG_URL', None)
        if remote_config_url is None:
            cls._remote_config_cache = {}
            return
        # Fast path: serve the cache without locking while it is still fresh.
        if time.time() - cls._cache_timestamp <= cls._CACHE_EXPIRATION_SECONDS:
            return
        if cls._cache_timestamp == 0:
            # Very first load: fetch synchronously (under the lock) so
            # startup reads see the remote values rather than defaults.
            with cls._lock:
                if cls._cache_timestamp == 0:
                    cls._refresh(remote_config_url)
            return
        # Stale-while-revalidate: callers get the (stale) cache immediately —
        # get_env_var runs inside async handlers, and a synchronous 5s fetch
        # under the lock would stall the event loop and serialize every
        # other caller behind it. A single daemon thread revalidates.
        with cls._lock:
            if cls._refresh_in_flight or (
                time.time() - cls._cache_timestamp <= cls._CACHE_EXPIRATION_SECONDS
            ):
                return
            cls._refresh_in_flight = True
        threading.Thread(
            target=cls._background_refresh,
            args=(remote_config_url,),
            name="remote-config-refresh",
            daemon=True,
        ).start()

    @classmethod
    def _background_refresh(cls, remote_config_url: str) -> None:
        try:
            with cls._lock:
                cls._refresh(remote_config_url)
        finally:
            cls._refresh_in_flight = False

    @classmethod
    def _refresh(cls, remote_config_url: str) -> None:
        """Fetch and install the remote config. Callers hold ``_lock``."""
        cls._cache_timestamp = time.time()
        try:
            logger.info("Fetching remote config from %s", redact_url(remote_config_url))
            response = requests.get(remote_config_url, timeout=5)
            logger.debug("Remote config response status: %s", response.status_code)
            response.raise_for_status()
            cls._remote_config_cache = cls._unwrap_remote_config(response.json())
        except (requests.exceptions.RequestException, json.JSONDecodeError):
            logger.exception("Error loading remote configuration")
            cls._remote_config_cache = {}

    @staticmethod
    def _unwrap_remote_config(payload):
        """Return the flat env-var mapping from a remote config payload.

        The remote config is expected to be a flat ``{KEY: value}`` object
        whose keys are env-var names. The companion configurator exports it
        wrapped in a ``{"configuration": {...}}`` envelope, so unwrap that
        single key transparently; otherwise the nested config keys (e.g.
        ``APP_TEAMS``) would never be found and the app would silently fall
        back to its defaults.

        Always returns a dict: a non-dict payload (a JSON list, string or
        bool the endpoint might serve) is dropped to ``{}`` so later
        ``cache.get(...)`` lookups can't raise ``AttributeError``.
        """
        if not isinstance(payload, dict):
            return {}
        if len(payload) == 1 and "configuration" in payload:
            inner = payload["configuration"]
            if isinstance(inner, dict):
                return inner
        return payload
