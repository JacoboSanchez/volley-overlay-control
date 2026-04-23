"""
Tests for WSControlClient message handling and send methods.
"""
import json
from unittest.mock import MagicMock

import pytest

from app.ws_client import WSControlClient


class TestWSControlClientMessages:
    """Tests for message handling and send methods in ws_client.py."""

    @pytest.fixture
    def client(self):
        return WSControlClient(
            overlay_id='test_overlay',
            ws_url='ws://localhost:9000/ws/control/test_overlay',
        )

    # -- send helpers ---------------------------------------------------------

    def test_send_returns_false_when_not_connected(self, client):
        """_send() should return False when not connected."""
        assert client.send_state({'score': 0}) is False

    def test_send_state_message_format(self, client):
        """send_state() should build a state_update message."""
        mock_ws = MagicMock()
        client._ws = mock_ws
        client._connected = True
        client.send_state({'score': 1})
        sent = json.loads(mock_ws.send.call_args[0][0])
        assert sent['type'] == 'state_update'
        assert sent['payload'] == {'score': 1}

    def test_send_visibility_message_format(self, client):
        """send_visibility() should build a visibility message."""
        mock_ws = MagicMock()
        client._ws = mock_ws
        client._connected = True
        client.send_visibility(True)
        sent = json.loads(mock_ws.send.call_args[0][0])
        assert sent['type'] == 'visibility'
        assert sent['show'] is True

    def test_send_get_state_message_format(self, client):
        """send_get_state() should send {"type": "get_state"}."""
        mock_ws = MagicMock()
        client._ws = mock_ws
        client._connected = True
        client.send_get_state()
        sent = json.loads(mock_ws.send.call_args[0][0])
        assert sent == {'type': 'get_state'}

    def test_send_raw_config_message_format(self, client):
        """send_raw_config() should wrap the payload correctly."""
        mock_ws = MagicMock()
        client._ws = mock_ws
        client._connected = True
        payload = {'model': {}}
        client.send_raw_config(payload)
        sent = json.loads(mock_ws.send.call_args[0][0])
        assert sent['type'] == 'raw_config'
        assert sent['payload'] == payload

    def test_send_marks_disconnected_on_ws_error(self, client):
        """_send() should set _connected=False when ws.send raises."""
        mock_ws = MagicMock()
        mock_ws.send.side_effect = Exception("broken pipe")
        client._ws = mock_ws
        client._connected = True
        result = client._send({'type': 'ping'})
        assert result is False
        assert client._connected is False
