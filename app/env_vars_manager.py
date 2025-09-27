import os
import requests
import json
import time
import logging

class EnvVarsManager:
    _remote_config_cache = {}
    _cache_timestamp = 0
    _CACHE_EXPIRATION_SECONDS = 10

    logger = logging.getLogger("EnvVarsManager")

    @classmethod
    def get_env_var(cls, key, default=None):
        cls._load_remote_config_if_needed()
        return cls._remote_config_cache.get(key, os.environ.get(key, default))

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
                    EnvVarsManager.logger.info(f"Fetching remote config to {remote_config_url}")
                    response = requests.get(remote_config_url, timeout=5)
                    EnvVarsManager.logger.debug(f"Remote config response: {response.status_code}")
                    response.raise_for_status()
                    cls._remote_config_cache = response.json()
                except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
                    EnvVarsManager.logger.error(f"Error loading remote configuration: {e}")
                    cls._remote_config_cache = {}
    