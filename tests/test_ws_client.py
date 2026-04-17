# tests/test_ws_client.py
"""Tests for WebSocket client and Backend WS integration."""
import pytest
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.backend import Backend
from app.conf import Conf
from app.ws_client import WSControlClient


# --- WSControlClient unit tests ---

class TestWSControlClient:
    """Tests for WSControlClient in isolation."""

    def test_initial_state(self):
        """Client starts disconnected."""
        client = WSControlClient("test", "ws://localhost:8002/ws/control/test")
        assert client.is_connected is False
        assert client.obs_client_count == 0

    def test_send_state_when_disconnected(self):
        """send_state returns False when not connected."""
        client = WSControlClient("test", "ws://localhost:8002/ws/control/test")
        assert client.send_state({"team_home": {"points": 5}}) is False

    def test_send_visibility_when_disconnected(self):
        """send_visibility returns False when not connected."""
        client = WSControlClient("test", "ws://localhost:8002/ws/control/test")
        assert client.send_visibility(True) is False

    def test_send_raw_config_when_disconnected(self):
        """send_raw_config returns False when not connected."""
        client = WSControlClient("test", "ws://localhost:8002/ws/control/test")
        assert client.send_raw_config({"model": {}}) is False

    def test_send_state_when_connected(self):
        """send_state returns True when connected with a mock socket."""
        client = WSControlClient("test", "ws://localhost:8002/ws/control/test")
        mock_ws = MagicMock()
        client._ws = mock_ws
        client._connected = True

        assert client.send_state({"team_home": {"points": 10}}) is True
        mock_ws.send.assert_called_once()

    def test_send_handles_exception(self):
        """send returns False and marks disconnected if socket raises."""
        client = WSControlClient("test", "ws://localhost:8002/ws/control/test")
        mock_ws = MagicMock()
        mock_ws.send.side_effect = ConnectionError("broken")
        client._ws = mock_ws
        client._connected = True

        assert client.send_state({"team_home": {"points": 10}}) is False
        assert client._connected is False

    def test_handle_connected_message(self):
        """_handle_message processes connected handshake."""
        client = WSControlClient("test", "ws://localhost:8002/ws/control/test")
        client._handle_message({
            "type": "connected",
            "protocol": 1,
            "overlay_id": "test",
            "obs_clients": 3,
            "current_state": {},
        })
        assert client.obs_client_count == 3

    def test_handle_ack_message(self):
        """_handle_message updates obs count from ack."""
        client = WSControlClient("test", "ws://localhost:8002/ws/control/test")
        client._handle_message({
            "type": "ack",
            "ref": "state_update",
            "obs_clients": 5,
        })
        assert client.obs_client_count == 5

    def test_handle_obs_event(self):
        """_handle_message updates obs count from obs_event."""
        callback = MagicMock()
        client = WSControlClient(
            "test", "ws://localhost:8002/ws/control/test",
            on_event=callback,
        )
        client._handle_message({
            "type": "obs_event",
            "event": "connected",
            "obs_clients": 2,
        })
        assert client.obs_client_count == 2
        callback.assert_called_once()

    def test_disconnect_cleans_up(self):
        """disconnect() clears connection state."""
        client = WSControlClient("test", "ws://localhost:8002/ws/control/test")
        mock_ws = MagicMock()
        client._ws = mock_ws
        client._connected = True
        client._stop_event.clear()

        client.disconnect()

        assert client.is_connected is False
        assert client._ws is None
        mock_ws.close.assert_called_once()


# --- Backend WS integration tests ---

@pytest.fixture
def mock_requests_session():
    """Fixture to mock the requests.Session object."""
    with patch('app.backend.requests.Session') as mock_session_class:
        mock_session_instance = mock_session_class.return_value
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'payload': {}}
        mock_session_instance.put.return_value = mock_response
        mock_session_instance.get.return_value = mock_response
        mock_session_instance.post.return_value = mock_response
        yield mock_session_instance


@pytest.fixture
def conf():
    return Conf()


@pytest.fixture
def backend(conf, mock_requests_session):
    return Backend(conf)


@patch.dict(os.environ, {"APP_CUSTOM_OVERLAY_URL": "http://localhost:8000"})
class TestBackendWSIntegration:
    """Tests for Backend's WebSocket-first behavior with external overlay server.

    These tests verify CustomOverlayBackend (HTTP/WebSocket to external server).
    APP_CUSTOM_OVERLAY_URL is set to force Backend to select CustomOverlayBackend
    instead of LocalOverlayBackend.
    """

    def _ensure_custom_overlay(self, backend, conf):
        """Helper: switch backend to CustomOverlayBackend for C- OID."""
        conf.oid = "C-test_overlay"
        backend._ensure_overlay_backend(conf.oid)

    def test_ws_client_initially_none(self, backend):
        """Backend starts with no WS client."""
        assert backend.ws_connected is False

    def test_init_ws_client_skips_non_custom(self, backend, conf):
        """init_ws_client does nothing for non-custom overlays."""
        conf.oid = "some_uno_token"
        backend.init_ws_client()
        assert backend.ws_connected is False

    def test_init_ws_client_discovers_url(
        self, backend, mock_requests_session, conf
    ):
        """init_ws_client probes /api/config and creates client if WS URL found."""
        self._ensure_custom_overlay(backend, conf)
        mock_requests_session.get.return_value.json.return_value = {
            "outputUrl": "http://localhost:8002/overlay/test_overlay",
            "availableStyles": ["default"],
            "controlWebSocketUrl": "ws://localhost:8002/ws/control/test_overlay",
        }

        with patch('app.ws_client.WSControlClient') as MockWSClient:
            mock_instance = MockWSClient.return_value
            backend.init_ws_client()

            MockWSClient.assert_called_once()
            mock_instance.connect.assert_called_once()
            assert backend._overlay._ws_client is mock_instance

    def test_init_ws_client_no_ws_url(
        self, backend, mock_requests_session, conf
    ):
        """init_ws_client falls back gracefully when no WS URL in config."""
        self._ensure_custom_overlay(backend, conf)
        mock_requests_session.get.return_value.json.return_value = {
            "outputUrl": "http://localhost:8002/overlay/test_overlay",
            "availableStyles": ["default"],
        }

        backend.init_ws_client()
        assert backend._overlay._ws_client is None

    def test_update_local_overlay_prefers_ws(
        self, backend, mock_requests_session, conf
    ):
        """update_local_overlay uses WS when connected."""
        self._ensure_custom_overlay(backend, conf)

        mock_ws = MagicMock()
        mock_ws.is_connected = True
        mock_ws.send_state.return_value = True
        backend._overlay._ws_client = mock_ws
        backend._customization_cache = {
            "Team 1 Text Name": "Local",
            "Team 2 Text Name": "Visitor",
            "Team 1 Color": "#060f8a",
            "Team 1 Text Color": "#ffffff",
            "Team 2 Color": "#ffffff",
            "Team 2 Text Color": "#000000",
            "Team 1 Logo": "",
            "Team 2 Logo": "",
            "Logos": "true",
            "Gradient": "true",
            "Height": 10,
            "Left-Right": -33,
            "Up-Down": -41.1,
            "Width": 30,
            "Color 1": "#2a2f35",
            "Text Color 1": "#ffffff",
            "Color 2": "#ffffff",
            "Text Color 2": "#2a2f35",
            "preferredStyle": "default",
        }

        backend.update_local_overlay({"Current Set": "1"})

        mock_ws.send_state.assert_called_once()
        # HTTP POST should NOT have been called
        state_calls = [
            c for c in mock_requests_session.post.call_args_list
            if '/api/state/' in str(c)
        ]
        assert len(state_calls) == 0

    def test_update_local_overlay_falls_back_to_http(
        self, backend, mock_requests_session, conf
    ):
        """update_local_overlay falls back to HTTP when WS not connected."""
        self._ensure_custom_overlay(backend, conf)

        mock_ws = MagicMock()
        mock_ws.is_connected = False
        backend._overlay._ws_client = mock_ws
        backend._customization_cache = {
            "Team 1 Text Name": "Local",
            "Team 2 Text Name": "Visitor",
            "Team 1 Color": "#060f8a",
            "Team 1 Text Color": "#ffffff",
            "Team 2 Color": "#ffffff",
            "Team 2 Text Color": "#000000",
            "Team 1 Logo": "",
            "Team 2 Logo": "",
            "Logos": "true",
            "Gradient": "true",
            "Height": 10,
            "Left-Right": -33,
            "Up-Down": -41.1,
            "Width": 30,
            "Color 1": "#2a2f35",
            "Text Color 1": "#ffffff",
            "Color 2": "#ffffff",
            "Text Color 2": "#2a2f35",
            "preferredStyle": "default",
        }

        backend.update_local_overlay({"Current Set": "1"})

        mock_ws.send_state.assert_not_called()
        # HTTP POST should have been called
        state_calls = [
            c for c in mock_requests_session.post.call_args_list
            if '/api/state/' in str(c)
        ]
        assert len(state_calls) == 1

    def test_change_visibility_prefers_ws(
        self, backend, mock_requests_session, conf
    ):
        """change_overlay_visibility uses WS when connected for custom overlays."""
        self._ensure_custom_overlay(backend, conf)

        mock_ws = MagicMock()
        mock_ws.is_connected = True
        mock_ws.send_visibility.return_value = True
        backend._overlay._ws_client = mock_ws

        backend.change_overlay_visibility(True)

        mock_ws.send_visibility.assert_called_once_with(True)
        mock_requests_session.put.assert_not_called()
        mock_requests_session.post.assert_not_called()

    def test_save_model_raw_config_prefers_ws(
        self, backend, mock_requests_session, conf
    ):
        """save_model sends raw_config via WS when connected."""
        self._ensure_custom_overlay(backend, conf)
        conf.multithread = False

        mock_ws = MagicMock()
        mock_ws.is_connected = True
        mock_ws.send_raw_config.return_value = True
        mock_ws.send_state.return_value = True
        backend._overlay._ws_client = mock_ws
        backend._customization_cache = {
            "Team 1 Text Name": "Local",
            "Team 2 Text Name": "Visitor",
            "Team 1 Color": "#060f8a",
            "Team 1 Text Color": "#ffffff",
            "Team 2 Color": "#ffffff",
            "Team 2 Text Color": "#000000",
            "Team 1 Logo": "",
            "Team 2 Logo": "",
            "Logos": "true",
            "Gradient": "true",
            "Height": 10,
            "Left-Right": -33,
            "Up-Down": -41.1,
            "Width": 30,
            "Color 1": "#2a2f35",
            "Text Color 1": "#ffffff",
            "Color 2": "#ffffff",
            "Text Color 2": "#2a2f35",
            "preferredStyle": "default",
        }

        backend.save_model({"Current Set": "1"}, simple=False)

        mock_ws.send_raw_config.assert_called_once()
        # Verify raw_config was sent with model key
        call_args = mock_ws.send_raw_config.call_args[0][0]
        assert "model" in call_args

    def test_close_ws_client(self, backend, conf):
        """close_ws_client disconnects and clears reference."""
        self._ensure_custom_overlay(backend, conf)
        mock_ws = MagicMock()
        backend._overlay._ws_client = mock_ws

        backend.close_ws_client()

        mock_ws.disconnect.assert_called_once()
        assert backend._overlay._ws_client is None
