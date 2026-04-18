"""External custom overlay backend (WebSocket-first, HTTP fallback)."""

import copy
import logging
from urllib.parse import urlparse

import requests
import requests.exceptions

from app.env_vars_manager import EnvVarsManager
from app.state import State

from app.overlay_backends.base import OverlayBackend
from app.overlay_backends.utils import split_custom_oid

logger = logging.getLogger(__name__)


class CustomOverlayBackend(OverlayBackend):
    """Communicates with an external overlay server via WebSocket + HTTP fallback."""

    def __init__(self, conf, session: requests.Session):
        self.conf = conf
        self.session = session
        self._ws_client = None
        self._obs_client_count = 0
        # Build overlay payload callback — set by Backend after construction
        self._build_payload = None

    # Backwards-compatible static helper (used elsewhere in the codebase).
    @staticmethod
    def get_overlay_id(oid: str):
        """Extract base_id and optional style from a custom OID."""
        return split_custom_oid(oid)

    def _base_url(self):
        return EnvVarsManager.get_custom_overlay_url().rstrip('/')

    def _auth_headers(self):
        """Return Authorization header when OVERLAY_SERVER_TOKEN is set.

        Sent per-request (not via ``session.headers``) because the same
        ``requests.Session`` is shared with the Uno backend, which must
        never receive this header.
        """
        token = EnvVarsManager.get_env_var('OVERLAY_SERVER_TOKEN', None)
        if token and token.strip():
            return {"Authorization": f"Bearer {token.strip()}"}
        return {}

    def _custom_id(self, oid=None):
        check_oid = oid if oid is not None else self.conf.oid
        cid, _ = split_custom_oid(check_oid)
        return cid

    def _style(self, oid=None):
        check_oid = oid if oid is not None else self.conf.oid
        _, style = split_custom_oid(check_oid)
        return style

    def _ws_send_raw_config(self, payload):
        """Send raw_config via WS if connected, else HTTP POST."""
        if self._ws_client and self._ws_client.is_connected:
            self._ws_client.send_raw_config(payload)
        else:
            custom_id = self._custom_id()
            try:
                self.session.post(
                    f"{self._base_url()}/api/raw_config/{custom_id}",
                    json=payload, timeout=2.0,
                    headers=self._auth_headers(),
                )
            except Exception as e:
                logger.error("Failed to save raw_config remote: %s", e)

    # -- WebSocket lifecycle --

    def init_ws_client(self, oid: str = None) -> None:
        self.close_ws_client()
        custom_id = self._custom_id(oid)
        base_url = self._base_url()
        try:
            resp = self.session.get(
                f"{base_url}/api/config/{custom_id}", timeout=5.0,
                headers=self._auth_headers(),
            )
            if resp.status_code == 200:
                ws_url = resp.json().get('controlWebSocketUrl')
                if ws_url:
                    from app.ws_client import WSControlClient
                    self._ws_client = WSControlClient(
                        overlay_id=custom_id,
                        ws_url=ws_url,
                        on_event=self._handle_ws_event,
                    )
                    self._ws_client.connect()
                    logger.info('WS client initialized for %s', custom_id)
        except Exception as e:
            logger.debug('WS discovery failed: %s', e)

    def close_ws_client(self) -> None:
        if self._ws_client:
            self._ws_client.disconnect()
            self._ws_client = None

    def shutdown(self) -> None:
        self.close_ws_client()

    @property
    def ws_connected(self) -> bool:
        return self._ws_client is not None and self._ws_client.is_connected

    @property
    def obs_client_count(self) -> int:
        return self._obs_client_count

    def _handle_ws_event(self, event: dict):
        etype = event.get('type')
        if etype in ('obs_event', 'ack', 'connected'):
            self._obs_client_count = event.get(
                'obs_clients', self._obs_client_count
            )

    @property
    def is_custom(self) -> bool:
        return True

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
        if not self.ws_connected and self._build_payload and get_model:
            current_model = get_model()
            if current_model:
                payload = self._build_payload(
                    current_model, force_visibility=show,
                )
                self.send_overlay_state(payload)

    # -- OverlayBackend interface --

    def save_model(self, current_model: dict) -> None:
        self._ws_send_raw_config({"model": current_model})

    def save_customization(self, data: dict) -> None:
        self._ws_send_raw_config({"customization": data})

    def change_visibility(self, show: bool) -> None:
        if self._ws_client and self._ws_client.is_connected:
            self._ws_client.send_visibility(show)

    def get_model(self, oid: str = None, save_result: bool = False) -> dict | None:
        custom_id = self._custom_id(oid)
        try:
            resp = self.session.get(
                f"{self._base_url()}/api/raw_config/{custom_id}", timeout=2.0,
                headers=self._auth_headers(),
            )
            if resp.status_code == 200:
                data = resp.json().get("model", {})
                if data:
                    return data
            return State().get_reset_model()
        except requests.exceptions.RequestException as e:
            logger.error("Network error fetching custom overlay model: %s", e)
            return None
        except Exception as e:
            logger.error("Failed to fetch custom overlay model: %s", e)
            return None

    def _get_default_customization(self, style, custom_id):
        """Return a default customization dict, persisting preferredStyle if needed."""
        from app.customization import Customization
        data = copy.copy(Customization.reset_state)
        if style and not data.get("preferredStyle"):
            data["preferredStyle"] = style
            try:
                self.session.post(
                    f"{self._base_url()}/api/raw_config/{custom_id}",
                    json={"customization": data}, timeout=2.0,
                    headers=self._auth_headers(),
                )
            except Exception as e:
                logger.warning("Failed to persist preferredStyle: %s", e)
        return data

    def get_customization(self, oid: str = None) -> dict | None:
        check_oid = oid if oid is not None else self.conf.oid
        custom_id = self._custom_id(check_oid)
        style = self._style(check_oid)

        try:
            resp = self.session.get(
                f"{self._base_url()}/api/raw_config/{custom_id}", timeout=2.0,
                headers=self._auth_headers(),
            )
            if resp.status_code == 200:
                data = resp.json().get("customization", {})
                if not data:
                    data = self._get_default_customization(style, custom_id)
                elif style and not data.get("preferredStyle"):
                    data["preferredStyle"] = style
                    try:
                        self.session.post(
                            f"{self._base_url()}/api/raw_config/{custom_id}",
                            json={"customization": data}, timeout=2.0,
                            headers=self._auth_headers(),
                        )
                    except Exception as e:
                        logger.warning("Failed to persist preferredStyle: %s", e)
                return data
        except Exception as e:
            logger.error("Failed to fetch custom overlay customization: %s", e)

        return self._get_default_customization(style, custom_id)

    def is_visible(self) -> bool:
        return True

    def get_available_styles(self, oid: str = None) -> list:
        custom_id = self._custom_id(oid)
        try:
            response = self.session.get(
                f"{self._base_url()}/api/config/{custom_id}", timeout=5.0,
                headers=self._auth_headers(),
            )
            if response.status_code == 200:
                return response.json().get('availableStyles', [])
        except Exception as e:
            logger.error("Error fetching available styles: %s", e)
        return []

    def fetch_output_token(self, oid: str = None) -> str | None:
        try:
            custom_id = self._custom_id(oid)
            url = f"{self._base_url()}/api/config/{custom_id}"
            response = self.session.get(
                url, timeout=5.0, headers=self._auth_headers(),
            )
            if response.status_code == 200:
                output_url = response.json().get('outputUrl')
                if output_url:
                    if EnvVarsManager.has_custom_overlay_output_url():
                        output_base = EnvVarsManager.get_custom_overlay_output_url().rstrip('/')
                        output_path = urlparse(output_url).path
                        output_url = f"{output_base}{output_path}"
                    return output_url
        except Exception as e:
            logger.error("Error fetching local output token: %s", e)
        return None

    def validate_oid(self, oid: str) -> State.OIDStatus:
        result = self.get_model(oid=oid)
        if result is not None:
            if result.get("game1State") is not None:
                return State.OIDStatus.DEPRECATED
            return State.OIDStatus.VALID
        return State.OIDStatus.INVALID

    def fetch_and_update_overlay_id(self, oid: str) -> None:
        logger.info('Custom overlay detected, skipping Uno ID fetch')

    def send_overlay_state(self, payload, **kwargs) -> None:
        """Push state to connected OBS clients via WS or HTTP fallback."""
        try:
            if self._ws_client and self._ws_client.is_connected:
                if self._ws_client.send_state(payload):
                    return
            custom_id = self._custom_id()
            self.session.post(
                f"{self._base_url()}/api/state/{custom_id}",
                json=payload, timeout=2.0,
                headers=self._auth_headers(),
            )
        except Exception as e:
            logger.error("Error updating local overlay: %s", e)

    def send_json_model(self, to_save: dict) -> None:
        pass  # Custom overlays don't use Uno's SetOverlayContent

    def reduce_games_to_one(self) -> None:
        pass  # Custom overlays don't use Uno's SetOverlayContent for partial updates
