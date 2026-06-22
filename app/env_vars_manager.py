import json
import logging
import os
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
        else:
            now = time.time()
            if now - cls._cache_timestamp > cls._CACHE_EXPIRATION_SECONDS:
                cls._cache_timestamp = now
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
