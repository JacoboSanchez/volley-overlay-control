import os
import requests
import json
import time
import logging

from app.logging_utils import redact_url

logger = logging.getLogger(__name__)


class EnvVarsManager:
    _remote_config_cache = {}
    _cache_timestamp = 0
    _CACHE_EXPIRATION_SECONDS = 10

    @classmethod
    def get_env_var(cls, key, default=None):
        cls._load_remote_config_if_needed()
        return cls._remote_config_cache.get(key, os.environ.get(key, default))

    @classmethod
    def get_custom_overlay_url(cls):
        return cls.get_env_var('APP_CUSTOM_OVERLAY_URL', 'http://localhost:8000')

    @classmethod
    def get_custom_overlay_output_url(cls):
        return cls.get_env_var('APP_CUSTOM_OVERLAY_OUTPUT_URL', cls.get_custom_overlay_url())

    @classmethod
    def has_custom_overlay_output_url(cls):
        """Return True when APP_CUSTOM_OVERLAY_OUTPUT_URL is explicitly configured."""
        cls._load_remote_config_if_needed()
        return 'APP_CUSTOM_OVERLAY_OUTPUT_URL' in cls._remote_config_cache or 'APP_CUSTOM_OVERLAY_OUTPUT_URL' in os.environ


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
                    cls._remote_config_cache = response.json()
                except (requests.exceptions.RequestException, json.JSONDecodeError):
                    logger.exception("Error loading remote configuration")
                    cls._remote_config_cache = {}
