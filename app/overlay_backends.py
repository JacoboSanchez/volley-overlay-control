"""Strategy pattern implementations for overlay communication.

Two overlay backends exist:
- UnoOverlayBackend: communicates with the overlays.uno cloud REST API
- LocalOverlayBackend: serves overlays locally using an embedded state store
  and OBS broadcast hub (absorbed from volleyball-scoreboard-overlay)
"""

import copy
import logging
import re
from abc import ABC, abstractmethod
from urllib.parse import urlparse

import requests
import requests.exceptions

from app.app_storage import AppStorage
from app.env_vars_manager import EnvVarsManager
from app.state import State

logger = logging.getLogger(__name__)


class OverlayBackend(ABC):
    """Abstract interface for overlay communication."""

    @abstractmethod
    def save_model(self, current_model: dict) -> None:
        """Persist the raw game model to the overlay backend."""

    @abstractmethod
    def save_customization(self, data: dict) -> None:
        """Persist customization data."""

    @abstractmethod
    def change_visibility(self, show: bool) -> None:
        """Toggle overlay visibility."""

    @abstractmethod
    def get_model(self, oid: str = None, save_result: bool = False) -> dict | None:
        """Retrieve the current raw game model."""

    @abstractmethod
    def get_customization(self, oid: str = None) -> dict | None:
        """Retrieve the current customization dict."""

    @abstractmethod
    def is_visible(self) -> bool:
        """Return whether the overlay is currently visible."""

    @abstractmethod
    def get_available_styles(self, oid: str = None) -> list:
        """Return list of available overlay styles."""

    @abstractmethod
    def fetch_output_token(self, oid: str = None) -> str | None:
        """Fetch the output URL or token for this overlay."""

    @abstractmethod
    def validate_oid(self, oid: str) -> State.OIDStatus:
        """Validate the OID and return a status."""

    @abstractmethod
    def fetch_and_update_overlay_id(self, oid: str) -> None:
        """Fetch the specific overlay layout ID from the provider."""

    @abstractmethod
    def send_overlay_state(self, payload: dict, force_visibility=None,
                           customization_state=None,
                           show_only_current_set=None) -> None:
        """Push a full overlay state update to connected displays."""

    @abstractmethod
    def send_json_model(self, to_save: dict) -> None:
        """Send a partial model update to the overlay provider."""

    @abstractmethod
    def reduce_games_to_one(self) -> None:
        """Reset scores of sets 2-5 to zero."""

    def push_model_update(self, current_model: dict, to_save: dict,
                          show_only_current_set=None) -> None:
        """Push a model update using the backend-appropriate mechanism.

        Subclasses override to send either a partial Uno model or a full
        overlay state payload for custom backends.
        """
        self.send_json_model(to_save)

    def on_customization_saved(self, get_model,
                               customization: dict) -> None:
        """Hook called after customization is persisted (no-op by default).

        *get_model* is a callable returning the current model dict.
        """

    def change_visibility_with_fallback(self, show: bool,
                                        get_model=None) -> None:
        """Toggle visibility with an optional HTTP fallback.

        *get_model* is a callable returning the current model dict (called
        lazily only when the fallback path is needed).  Default
        implementation delegates to ``change_visibility``.
        """
        self.change_visibility(show)

    def init_ws_client(self, oid: str = None) -> None:
        """Initialize WebSocket client (no-op by default)."""

    def close_ws_client(self) -> None:
        """Close WebSocket client (no-op by default)."""

    def shutdown(self) -> None:
        """Clean up resources."""
        self.close_ws_client()

    @property
    def is_custom(self) -> bool:
        return False

    @property
    def ws_connected(self) -> bool:
        return False

    @property
    def obs_client_count(self) -> int:
        return 0


# ---------------------------------------------------------------------------
# Uno (cloud) overlay backend
# ---------------------------------------------------------------------------


class UnoOverlayBackend(OverlayBackend):
    """Communicates with the overlays.uno cloud REST API."""

    def __init__(self, conf, session: requests.Session):
        self.conf = conf
        self.session = session

    def _send_command(self, command, content="", oid=None):
        target_oid = oid if oid is not None else self.conf.oid
        payload = {"command": command, "id": self.conf.id, "content": content}
        return self._do_request(target_oid, payload)

    def _send_command_with_value(self, command, value="", oid=None):
        target_oid = oid if oid is not None else self.conf.oid
        payload = {"command": command, "value": value}
        return self._do_request(target_oid, payload)

    def _do_request(self, oid, payload):
        url = f'https://app.overlays.uno/apiv2/controlapps/{oid}/api'
        try:
            response = self.session.put(url, json=payload, timeout=5.0)
            if response.status_code >= 300:
                logger.warning("response %s: '%s'", response.status_code, response.text)
            return response
        except requests.exceptions.RequestException as e:
            logger.error("Network error in _do_request: %s", e)
            return _mock_response(500)

    # -- OverlayBackend interface --

    def save_model(self, current_model: dict) -> None:
        AppStorage.save(AppStorage.Category.CURRENT_MODEL, current_model, oid=self.conf.oid)

    def save_customization(self, data: dict) -> None:
        self._send_command_with_value("SetCustomization", data)

    def change_visibility(self, show: bool) -> None:
        command = "ShowOverlay" if show else "HideOverlay"
        self._send_command(command)

    def get_model(self, oid: str = None, save_result: bool = False) -> dict | None:
        target_oid = oid if oid is not None else self.conf.oid
        cached = AppStorage.load(AppStorage.Category.CURRENT_MODEL, oid=target_oid)
        if cached is not None:
            return cached

        response = self._send_command("GetOverlayContent", oid=target_oid)
        if response.status_code == 200:
            result = response.json().get('payload')
            if save_result and result:
                AppStorage.save(AppStorage.Category.CURRENT_MODEL, result, oid=target_oid)
            return result
        return None

    def get_customization(self, oid: str = None) -> dict | None:
        response = self._send_command("GetCustomization", oid=oid)
        if response.status_code == 200:
            return response.json().get('payload')
        return None

    def is_visible(self) -> bool:
        response = self._send_command("GetOverlayVisibility")
        if response.status_code == 200:
            return response.json().get('payload', False)
        return False

    def get_available_styles(self, oid: str = None) -> list:
        return []

    def fetch_output_token(self, oid: str = None) -> str | None:
        target_oid = oid if oid is not None else self.conf.oid
        try:
            url = f'https://app.overlays.uno/apiv2/controlapps/{target_oid}'
            response = self.session.get(url, timeout=5.0)
            if response.status_code == 200:
                output_url = response.json().get('outputUrl')
                if output_url:
                    match = re.search(r'/output/([^/?]+)', output_url)
                    if match:
                        return match.group(1)
            else:
                logger.warning("Failed to fetch output token for OID %s: %s",
                               target_oid, response.status_code)
        except requests.exceptions.RequestException as e:
            logger.error("Network error fetching output token: %s", e)
        except Exception as e:
            logger.error("Error fetching output token: %s", e)
        return None

    def validate_oid(self, oid: str) -> State.OIDStatus:
        self.fetch_and_update_overlay_id(oid)
        result = self.get_model(oid=oid, save_result=True)
        if result is not None:
            if result.get("game1State") is not None:
                return State.OIDStatus.DEPRECATED
            return State.OIDStatus.VALID
        return State.OIDStatus.INVALID

    def fetch_and_update_overlay_id(self, oid: str) -> None:
        payload = {"command": "GetOverlays", "value": ""}
        response = self._do_request(oid, payload)
        if hasattr(response, 'status_code') and response.status_code == 200:
            result = response.json().get('payload')
            if result and isinstance(result, list) and len(result) > 0:
                overlay_id = result[0].get('id')
                if overlay_id:
                    self.conf.id = overlay_id
                    logger.info('Updated conf.id to %s', overlay_id)

    def send_overlay_state(self, payload, **kwargs) -> None:
        pass  # Uno overlays don't use this path

    def send_json_model(self, to_save: dict) -> None:
        self._send_command("SetOverlayContent", to_save)

    def reduce_games_to_one(self) -> None:
        scores_to_reset = {
            State.T1SET5_INT: '0', State.T2SET5_INT: '0',
            State.T1SET4_INT: '0', State.T2SET4_INT: '0',
            State.T1SET3_INT: '0', State.T2SET3_INT: '0',
            State.T1SET2_INT: '0', State.T2SET2_INT: '0',
        }
        self.send_json_model(scores_to_reset)


# ---------------------------------------------------------------------------
# Local overlay backend (absorbed from volleyball-scoreboard-overlay)
# ---------------------------------------------------------------------------


class LocalOverlayBackend(OverlayBackend):
    """Serves overlays locally using an embedded state store and broadcast hub.

    Replaces the old ``CustomOverlayBackend`` which communicated with a
    separate overlay server process via WebSocket + HTTP.  Now all overlay
    state management, persistence, and OBS broadcasting happen in-process.
    """

    def __init__(self, conf, state_store, broadcast_hub):
        self.conf = conf
        self._store = state_store
        self._broadcast = broadcast_hub
        # Build overlay payload callback — set by Backend after construction
        self._build_payload = None

    @staticmethod
    def get_overlay_id(oid: str):
        """Extract base_id and optional style from a custom OID."""
        raw_id = str(oid)[2:]  # Remove "C-" prefix
        parts = raw_id.split('/', 1)
        return parts[0], (parts[1] if len(parts) > 1 else None)

    def _custom_id(self, oid=None):
        check_oid = oid if oid is not None else self.conf.oid
        cid, _ = self.get_overlay_id(check_oid)
        return cid

    def _style(self, oid=None):
        check_oid = oid if oid is not None else self.conf.oid
        _, style = self.get_overlay_id(check_oid)
        return style

    # -- Lifecycle (no-ops — everything is local) ---

    def init_ws_client(self, oid: str = None) -> None:
        # Ensure the overlay exists in the state store
        custom_id = self._custom_id(oid)
        self._store.ensure_overlay(custom_id)

    def close_ws_client(self) -> None:
        pass

    def shutdown(self) -> None:
        pass

    @property
    def is_custom(self) -> bool:
        return True

    @property
    def ws_connected(self) -> bool:
        return True  # Always "connected" since it's local

    @property
    def obs_client_count(self) -> int:
        custom_id = self._custom_id()
        return self._broadcast.get_client_count(custom_id)

    # -- Push hooks ---

    def push_model_update(self, current_model, to_save,
                          show_only_current_set=None):
        if self._build_payload:
            payload = self._build_payload(
                current_model, show_only_current_set=show_only_current_set,
            )
            self.send_overlay_state(payload)

    def on_customization_saved(self, get_model, customization):
        if self._build_payload and get_model:
            current_model = get_model()
            if current_model:
                payload = self._build_payload(
                    current_model, customization_state=customization,
                )
                self.send_overlay_state(payload)

    def change_visibility_with_fallback(self, show, get_model=None):
        self.change_visibility(show)

    # -- OverlayBackend interface --

    def save_model(self, current_model: dict) -> None:
        custom_id = self._custom_id()
        self._store.set_raw_config(custom_id, model=current_model)

    def save_customization(self, data: dict) -> None:
        custom_id = self._custom_id()
        self._store.set_raw_config(custom_id, customization=data)

    def change_visibility(self, show: bool) -> None:
        custom_id = self._custom_id()
        self._store.set_visibility(custom_id, show)

    def get_model(self, oid: str = None, save_result: bool = False) -> dict | None:
        custom_id = self._custom_id(oid)
        self._store.ensure_overlay(custom_id)
        raw = self._store.get_raw_config(custom_id)
        data = raw.get("model", {})
        if data:
            return data
        return State().get_reset_model()

    def get_customization(self, oid: str = None) -> dict | None:
        check_oid = oid if oid is not None else self.conf.oid
        custom_id = self._custom_id(check_oid)
        style = self._style(check_oid)

        self._store.ensure_overlay(custom_id)
        raw = self._store.get_raw_config(custom_id)
        data = raw.get("customization", {})

        if not data:
            data = self._get_default_customization(style, custom_id)
        elif style and not data.get("preferredStyle"):
            data["preferredStyle"] = style
            self._store.set_raw_config(custom_id, customization=data)

        return data

    def _get_default_customization(self, style, custom_id):
        """Return a default customization dict, persisting preferredStyle if needed."""
        from app.customization import Customization
        data = copy.copy(Customization.reset_state)
        if style and not data.get("preferredStyle"):
            data["preferredStyle"] = style
            self._store.set_raw_config(custom_id, customization=data)
        return data

    def is_visible(self) -> bool:
        return True

    def get_available_styles(self, oid: str = None) -> list:
        return self._store.get_available_styles_list()

    def fetch_output_token(self, oid: str = None) -> str | None:
        custom_id = self._custom_id(oid)
        output_key = self._store.get_output_key(custom_id)
        # Build the output URL using the configured public URL or a relative path
        public_url = EnvVarsManager.get_env_var("OVERLAY_PUBLIC_URL", "")
        if public_url:
            base = public_url.rstrip("/")
            return f"{base}/overlay/{output_key}"
        return f"/overlay/{output_key}"

    def validate_oid(self, oid: str) -> State.OIDStatus:
        custom_id = self._custom_id(oid)
        self._store.ensure_overlay(custom_id)
        return State.OIDStatus.VALID

    def fetch_and_update_overlay_id(self, oid: str) -> None:
        logger.info('Local overlay detected, skipping Uno ID fetch')

    def send_overlay_state(self, payload, **kwargs) -> None:
        """Deep-merge payload into local overlay state and broadcast to OBS."""
        custom_id = self._custom_id()
        self._store.update_state_sync(custom_id, payload)

    def send_json_model(self, to_save: dict) -> None:
        pass  # Local overlays don't use Uno's SetOverlayContent

    def reduce_games_to_one(self) -> None:
        pass  # Local overlays don't use Uno's SetOverlayContent for partial updates


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_response(status_code=200, payload=None):
    """Create a minimal response-like object for error paths."""
    body = payload or {}
    return type('MockResponse', (object,), {
        'status_code': status_code,
        'text': '',
        'json': lambda self: body,
    })()


def is_custom_overlay(oid: str) -> bool:
    """Check whether an OID refers to a custom (local) overlay."""
    return oid is not None and str(oid).upper().startswith("C-")
