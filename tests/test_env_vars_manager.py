import json
import os
import unittest
from unittest.mock import Mock, patch

import requests

from app.env_vars_manager import EnvVarsManager


class TestEnvVarsManager(unittest.TestCase):

    def setUp(self):
        # Clear cache before each test
        EnvVarsManager._remote_config_cache = {}
        EnvVarsManager._cache_timestamp = 0

    @patch.dict(os.environ, {"REMOTE_CONFIG_URL": "http://fake-url.com/config.json"})
    @patch('requests.get')
    def test_get_env_var_with_remote_config(self, mock_get):
        # Mock the remote config
        remote_config = {'TEST_VAR': 'remote_value'}
        mock_response = Mock()
        mock_response.json.return_value = remote_config
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        # Get the environment variable
        value = EnvVarsManager.get_env_var('TEST_VAR')

        # Assert that the value from the remote config is returned
        self.assertEqual(value, 'remote_value')

    @patch.dict(os.environ, {"TEST_VAR": "local_value"})
    def test_get_env_var_without_remote_config(self):
        # Get the environment variable
        value = EnvVarsManager.get_env_var('TEST_VAR')

        # Assert that the local environment variable is returned
        self.assertEqual(value, 'local_value')

    @patch.dict(os.environ, {"REMOTE_CONFIG_URL": "http://fake-url.com/config.json", "TEST_VAR": "local_value"})
    @patch('requests.get')
    def test_remote_config_overrides_local_env(self, mock_get):
        # Mock the remote config
        remote_config = {'TEST_VAR': 'remote_value'}
        mock_response = Mock()
        mock_response.json.return_value = remote_config
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        # Get the environment variable
        value = EnvVarsManager.get_env_var('TEST_VAR')

        # Assert that the remote value is returned
        self.assertEqual(value, 'remote_value')

    @patch.dict(os.environ, {"REMOTE_CONFIG_URL": "http://fake-url.com/config.json"})
    @patch('requests.get')
    def test_remote_config_wrapped_in_configuration_envelope(self, mock_get):
        # The companion configurator exports a {"configuration": {...}} envelope.
        remote_config = {'configuration': {'TEST_VAR': 'remote_value'}}
        mock_response = Mock()
        mock_response.json.return_value = remote_config
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        # The nested env var is resolved as if it were at the top level.
        self.assertEqual(EnvVarsManager.get_env_var('TEST_VAR'), 'remote_value')

    @patch.dict(os.environ, {"REMOTE_CONFIG_URL": "http://fake-url.com/config.json"})
    @patch('requests.get')
    def test_remote_config_envelope_with_extra_keys_not_unwrapped(self, mock_get):
        # A "configuration" key alongside other top-level keys is ambiguous,
        # so it is treated as a literal flat config (left unwrapped).
        remote_config = {'configuration': {'NESTED': 'x'}, 'TEST_VAR': 'flat_value'}
        mock_response = Mock()
        mock_response.json.return_value = remote_config
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        self.assertEqual(EnvVarsManager.get_env_var('TEST_VAR'), 'flat_value')

    @patch.dict(os.environ, {"REMOTE_CONFIG_URL": "http://fake-url.com/config.json", "TEST_VAR": "local_value"})
    @patch('requests.get')
    def test_remote_config_non_dict_payload_falls_back_to_local(self, mock_get):
        # A valid-JSON-but-non-dict payload (list/str/bool) must not crash
        # later cache.get() lookups; it is dropped so local env is used.
        mock_response = Mock()
        mock_response.json.return_value = ["not", "a", "dict"]
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        self.assertEqual(EnvVarsManager.get_env_var('TEST_VAR'), 'local_value')

    @patch.dict(os.environ, {"REMOTE_CONFIG_URL": "http://invalid-url.com/config.json", "TEST_VAR": "local_value"})
    @patch('requests.get')
    def test_invalid_remote_url(self, mock_get):
        # Mock a request exception
        mock_get.side_effect = requests.exceptions.RequestException("Connection error")

        # Get the environment variable
        value = EnvVarsManager.get_env_var('TEST_VAR')

        # Assert that the local value is returned
        self.assertEqual(value, 'local_value')

    @patch.dict(os.environ, {"REMOTE_CONFIG_URL": "http://fake-url.com/malformed.json", "TEST_VAR": "local_value"})
    @patch('requests.get')
    def test_malformed_remote_json(self, mock_get):
        # Mock a malformed JSON response
        mock_response = Mock()
        mock_response.json.side_effect = json.JSONDecodeError("Expecting value", "", 0)
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        # Get the environment variable
        value = EnvVarsManager.get_env_var('TEST_VAR')

        # Assert that the local value is returned
        self.assertEqual(value, 'local_value')

if __name__ == '__main__':
    unittest.main()


def test_stale_cache_is_served_while_revalidating(monkeypatch):
    """Once populated, a stale cache is returned immediately and the refetch
    happens on a background thread — a slow remote config must not block
    the caller (the event loop) for its full timeout."""
    import threading
    import time as time_mod
    from unittest.mock import patch

    from app.env_vars_manager import EnvVarsManager

    monkeypatch.setenv("REMOTE_CONFIG_URL", "http://config.example/env.json")
    EnvVarsManager._remote_config_cache = {"KEY": "stale-value"}
    EnvVarsManager._cache_timestamp = time_mod.time() - 3600  # long stale
    EnvVarsManager._refresh_in_flight = False

    release = threading.Event()
    fetched = threading.Event()

    class SlowResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"KEY": "fresh-value"}

    def slow_get(url, timeout):
        fetched.set()
        release.wait(5)
        return SlowResponse()

    with patch("app.env_vars_manager.requests.get", side_effect=slow_get):
        start = time_mod.time()
        value = EnvVarsManager.get_env_var("KEY")
        elapsed = time_mod.time() - start
        # Served the stale value without waiting on the in-flight fetch.
        assert value == "stale-value"
        assert elapsed < 1.0
        assert fetched.wait(2)
        release.set()
        # The background refresh eventually installs the fresh value.
        deadline = time_mod.time() + 5
        while time_mod.time() < deadline:
            if EnvVarsManager._remote_config_cache.get("KEY") == "fresh-value":
                break
            time_mod.sleep(0.02)
        assert EnvVarsManager._remote_config_cache.get("KEY") == "fresh-value"

    EnvVarsManager._remote_config_cache = {}
    EnvVarsManager._cache_timestamp = 0
    EnvVarsManager._refresh_in_flight = False
