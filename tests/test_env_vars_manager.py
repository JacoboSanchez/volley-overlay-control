import unittest
from unittest.mock import patch, Mock
import os
import json
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