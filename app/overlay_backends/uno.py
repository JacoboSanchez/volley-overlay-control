"""overlays.uno cloud REST backend."""

import logging
import re

import requests
import requests.exceptions

from app.app_storage import AppStorage
from app.state import State

from app.overlay_backends.base import OverlayBackend
from app.overlay_backends.utils import _mock_response

logger = logging.getLogger(__name__)


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
