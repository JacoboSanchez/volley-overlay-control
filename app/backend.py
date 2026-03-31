import requests
import requests.exceptions
import copy
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse
from app.state import State
from app.app_storage import AppStorage
from app.env_vars_manager import EnvVarsManager
import os
import json

from app.app_storage import AppStorage

class Backend:
    logger = logging.getLogger(__name__)

    def __init__(self, config):
        self.conf = config
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': self.conf.rest_user_agent,
            'Content-Type': 'application/json',
            'Accept': 'application/json, text/plain, */*'
        })
        # Initialize a thread pool with a maximum number of workers (e.g., 5)
        # This prevents uncontrolled thread creation during rapid changes.
        self.executor = ThreadPoolExecutor(max_workers=5)
        self._customization_cache = None
        self._ws_client = None
        self._obs_client_count = 0

    # -- WebSocket lifecycle -------------------------------------------------

    def init_ws_client(self, oid=None):
        """Probe the overlay server for WS support and connect if available."""
        check_oid = oid if oid is not None else self.conf.oid
        if not self.is_custom_overlay(check_oid):
            return
        self.close_ws_client()
        custom_id, _ = self.get_custom_overlay_id(check_oid)
        base_url = EnvVarsManager.get_custom_overlay_url().rstrip('/')
        try:
            resp = self.session.get(
                f"{base_url}/api/config/{custom_id}", timeout=5.0
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
                    Backend.logger.info(
                        'WS client initialized for %s', custom_id
                    )
                    return
        except Exception as e:
            Backend.logger.debug('WS discovery failed: %s', e)

    def close_ws_client(self):
        """Disconnect any active WS client."""
        if self._ws_client:
            self._ws_client.disconnect()
            self._ws_client = None

    @property
    def ws_connected(self):
        """True if a WebSocket connection to the overlay is active."""
        return self._ws_client is not None and self._ws_client.is_connected

    @property
    def obs_client_count(self):
        """Number of OBS browser clients connected to the overlay."""
        return self._obs_client_count

    def _handle_ws_event(self, event: dict):
        """Callback for incoming overlay→controller WS messages."""
        etype = event.get('type')
        if etype in ('obs_event', 'ack', 'connected'):
            self._obs_client_count = event.get(
                'obs_clients', self._obs_client_count
            )

    # -- helpers ------------------------------------------------------------

    def _build_overlay_payload(
        self, current_model,
        force_visibility=None,
        customization_state=None,
        show_only_current_set=None,
    ):
        """Build the standardized overlay state JSON payload."""
        from app.customization import Customization

        if customization_state is None:
            customization_state = (
                self._customization_cache
                if self._customization_cache is not None
                else (self.get_current_customization() or {})
            )
        cust = Customization(customization_state)

        def get_set_history(team):
            return {
                f"set_{i}": int(
                    current_model.get(
                        f'Team {team} Game {i} Score', 0
                    )
                )
                for i in range(1, 6)
            }

        current_set = int(
            current_model.get(State.CURRENT_SET_INT, 1)
        )

        payload = {
            "match_info": {
                "tournament": "Superliga Masculina",
                "phase": "Playoffs",
                "best_of_sets": int(self.conf.sets),
                "current_set": current_set,
            },
            "team_home": {
                "name": cust.get_team_name(1),
                "short_name": (
                    cust.get_team_name(1)[:3].upper()
                    if cust.get_team_name(1) else "HOM"
                ),
                "color_primary": cust.get_team_color(1),
                "color_secondary": cust.get_team_text_color(1),
                "logo_url": cust.get_team_logo(1),
                "sets_won": int(
                    current_model.get(State.T1SETS_INT, 0)
                ),
                "points": int(
                    current_model.get(
                        f'Team 1 Game {current_set} Score', 0
                    )
                ),
                "serving": (
                    current_model.get(State.SERVE) == State.SERVE_1
                ),
                "timeouts_taken": int(
                    current_model.get(State.T1TIMEOUTS_INT, 0)
                ),
                "set_history": get_set_history(1),
            },
            "team_away": {
                "name": cust.get_team_name(2),
                "short_name": (
                    cust.get_team_name(2)[:3].upper()
                    if cust.get_team_name(2) else "AWA"
                ),
                "color_primary": cust.get_team_color(2),
                "color_secondary": cust.get_team_text_color(2),
                "logo_url": cust.get_team_logo(2),
                "sets_won": int(
                    current_model.get(State.T2SETS_INT, 0)
                ),
                "points": int(
                    current_model.get(
                        f'Team 2 Game {current_set} Score', 0
                    )
                ),
                "serving": (
                    current_model.get(State.SERVE) == State.SERVE_2
                ),
                "timeouts_taken": int(
                    current_model.get(State.T2TIMEOUTS_INT, 0)
                ),
                "set_history": get_set_history(2),
            },
            "overlay_control": {
                "show_bottom_ticker": False,
                "ticker_message": "",
                "show_player_stats": False,
                "player_stats_data": None,
                "geometry": {
                    "width": cust.get_width(),
                    "height": cust.get_height(),
                    "xpos": cust.get_hpos(),
                    "ypos": cust.get_vpos(),
                },
                "colors": {
                    "set_bg": cust.get_set_color(),
                    "set_text": cust.get_set_text_color(),
                    "game_bg": cust.get_game_color(),
                    "game_text": cust.get_game_text_color(),
                },
                "preferredStyle": cust.get_preferred_style(),
                "show_logos": cust.is_show_logos() not in (False, "false", "False"),
            },
        }

        if show_only_current_set is not None:
            payload["match_info"][
                "show_only_current_set"
            ] = show_only_current_set

        if force_visibility is not None:
            payload["overlay_control"][
                "show_main_scoreboard"
            ] = force_visibility

        return payload

    def is_custom_overlay(self, oid=None):
        check_oid = oid if oid is not None else self.conf.oid
        return check_oid is not None and str(check_oid).upper().startswith("C-")

    def get_custom_overlay_id(self, oid=None):
        check_oid = oid if oid is not None else self.conf.oid
        if self.is_custom_overlay(check_oid):
            raw_id = str(check_oid)[2:] # Remove "C-" prefix
            parts = raw_id.split('/', 1)
            base_id = parts[0]
            style = parts[1] if len(parts) > 1 else None
            return base_id, style
        return check_oid, None

    def save_model(self, current_model, simple):
        Backend.logger.info('saving model...')
        
        # Uno overlays store in user session, custom overlays store globally
        if self.is_custom_overlay(self.conf.oid):
            raw_payload = {"model": current_model}
            # Prefer WS for raw_config persistence
            if self._ws_client and self._ws_client.is_connected:
                self._ws_client.send_raw_config(raw_payload)
            else:
                custom_id, _ = self.get_custom_overlay_id(self.conf.oid)
                base_url = EnvVarsManager.get_custom_overlay_url().rstrip('/')
                try:
                    self.session.post(f"{base_url}/api/raw_config/{custom_id}", json=raw_payload, timeout=2.0)
                except Exception as e:
                    Backend.logger.error(f"Failed to save custom overlay model remote: {e}")
        else:
            AppStorage.save(AppStorage.Category.CURRENT_MODEL, current_model, oid=self.conf.oid)
            
        to_save = copy.copy(current_model)
        if (simple):
            to_save = State.simplify_model(to_save)
            
        # Explicitly set Sets Display for the new overlay ID
        if self.conf.id == State.CHAMPIONSHIP_LAYOUT_ID:
            to_save["Sets Display"] = str(to_save.get(State.CURRENT_SET_INT, "1"))
            
        if self.conf.multithread:
            if self.is_custom_overlay():
                self.executor.submit(self.update_local_overlay, current_model, None, None, simple)
            else:
                self.executor.submit(self.save_json_model, to_save)
        else:
            if self.is_custom_overlay():
                self.update_local_overlay(current_model, None, None, simple)
            else:
                self.save_json_model(to_save)
        Backend.logger.info('saved')
    def reduce_games_to_one(self):
        """
        Resets the scores of sets 2, 3, 4, and 5 to zero in a single API call.
        """
        scores_to_reset = {
            State.T1SET5_INT: '0', State.T2SET5_INT: '0',
            State.T1SET4_INT: '0', State.T2SET4_INT: '0',
            State.T1SET3_INT: '0', State.T2SET3_INT: '0',
            State.T1SET2_INT: '0', State.T2SET2_INT: '0'
        }
        self.save_json_model(scores_to_reset)

    def save_json_model(self, to_save):
        Backend.logger.info('saving JSON model...')
        return self.send_command_with_id_and_content("SetOverlayContent", to_save)

    def save_json_customization(self, to_save):
        Backend.logger.info('saving JSON customization...')
        self._customization_cache = to_save

        # update local overlay as well, fetching current state if custom
        if self.is_custom_overlay():
            raw_payload = {"customization": to_save}
            # Prefer WS for raw_config persistence
            if self._ws_client and self._ws_client.is_connected:
                self._ws_client.send_raw_config(raw_payload)
            else:
                custom_id, _ = self.get_custom_overlay_id(self.conf.oid)
                base_url = EnvVarsManager.get_custom_overlay_url().rstrip('/')
                try:
                    self.session.post(f"{base_url}/api/raw_config/{custom_id}", json=raw_payload, timeout=2.0)
                except Exception as e:
                    Backend.logger.error(f"Failed to save custom overlay customization remote: {e}")
                
            current_model = self.get_current_model(self.conf.oid)
            if current_model:
                if self.conf.multithread:
                    self.executor.submit(self.update_local_overlay, current_model, None, to_save, None)
                else:
                    self.update_local_overlay(current_model, None, to_save, None)
            return type('MockResponse', (object,), {'status_code': 200, 'json': lambda self: {'payload': {}}})()
        
        return self.send_command_with_value("SetCustomization", to_save)

    def change_overlay_visibility(self, show):
        Backend.logger.info('changing overlay visibility, show: %s', show)
        command = "HideOverlay"
        if show:
            command = "ShowOverlay"

        if self.is_custom_overlay():
            # Prefer WS for direct visibility toggle
            if self._ws_client and self._ws_client.is_connected:
                self._ws_client.send_visibility(show)
                return type('MockResponse', (object,), {'status_code': 200, 'json': lambda self: {'payload': {}}})()
            current_model = self.get_current_model(self.conf.oid)
            if current_model:
                if self.conf.multithread:
                    self.executor.submit(self.update_local_overlay, current_model, show, None, None)
                else:
                    self.update_local_overlay(current_model, show, None, None)
            return type('MockResponse', (object,), {'status_code': 200, 'json': lambda self: {'payload': {}}})()

        return self.send_command_with_id_and_content(command)

    def send_command_with_value(self, command, value="", customOid=None):
        oid = customOid if customOid is not None else self.conf.oid
        jsonin = {"command": command, "value": value}
        return self.do_send_request(oid, jsonin)

    def send_command_with_id_and_content(self, command, content="", customOid=None):
        oid = customOid if customOid is not None else self.conf.oid
        jsonin = {"command": command,  "id": self.conf.id, "content": content}
        return self.do_send_request(oid, jsonin)

    def do_send_request(self, oid, jsonin):
        logging.debug("Sending [%s] via Session", jsonin)
        if self.is_custom_overlay(oid):
             return type('MockResponse', (object,), {'status_code': 200, 'json': lambda self: {'payload': {}}})()

        url = f'https://app.overlays.uno/apiv2/controlapps/{oid}/api'
        try:
            # Added a 5.0 second timeout to prevent blocking
            response = self.session.put(url, json=jsonin, timeout=5.0)
            return self.process_response(response)
        except requests.exceptions.RequestException as e:
            Backend.logger.error(f"Network error in do_send_request: {e}")
            # Return a mock object or None that the app can handle in case of a network error
            return type('MockResponse', (object,), {'status_code': 500, 'text': str(e), 'json': lambda self: {}})()

    def get_current_model(self, customOid=None, saveResult=False):
        oid = customOid if customOid is not None else self.conf.oid
        Backend.logger.info('getting state for oid %s', oid)
        
        if self.is_custom_overlay(oid):
            custom_id, _ = self.get_custom_overlay_id(oid)
            base_url = EnvVarsManager.get_custom_overlay_url().rstrip('/')
            try:
                resp = self.session.get(f"{base_url}/api/raw_config/{custom_id}", timeout=2.0)
                if resp.status_code == 200:
                    data = resp.json().get("model", {})
                    if data:
                        return data
                return State().get_reset_model()
            except requests.exceptions.RequestException as e:
                Backend.logger.error(f"Network error fetching custom overlay model: {e}")
                return None
            except Exception as e:
                Backend.logger.error(f"Failed to fetch custom overlay model: {e}")
                return None

        currentModel = AppStorage.load(AppStorage.Category.CURRENT_MODEL, oid=oid)
        if currentModel is not None:
            logging.info('Using stored model')
            logging.debug(currentModel)
            return currentModel
        
        response = self.send_command_with_id_and_content("GetOverlayContent", customOid=oid)
        if response.status_code == 200:
            result = response.json().get('payload')
            if saveResult and result:
                AppStorage.save(AppStorage.Category.CURRENT_MODEL, result, oid=oid)
            return result
        return None

    def get_current_customization(self, customOid=None):
        Backend.logger.info('getting customization')
        
        if self.is_custom_overlay(customOid):
            custom_id, style = self.get_custom_overlay_id(customOid)
            base_url = EnvVarsManager.get_custom_overlay_url().rstrip('/')
            try:
                resp = self.session.get(f"{base_url}/api/raw_config/{custom_id}", timeout=2.0)
                if resp.status_code == 200:
                    data = resp.json().get("customization", {})
                    # If the OID included a /style and we don't have a preferred style explicitly saved, or we want OID to overwrite:
                    # Let's see if we should set it. If data is empty we just use reset_state.
                    # We will always set preferredStyle if style is provided in OID
                    if not data:
                        from app.customization import Customization
                        data = copy.copy(Customization.reset_state)

                    # Only use the OID style as the initial default when no
                    # preferredStyle has been explicitly saved yet.  Once the
                    # user picks a style via the UI it must be respected.
                    if style and not data.get("preferredStyle"):
                        data["preferredStyle"] = style
                        try:
                            self.session.post(f"{base_url}/api/raw_config/{custom_id}", json={"customization": data}, timeout=2.0)
                        except Exception as persist_err:
                            Backend.logger.warning(f"Failed to persist preferredStyle update: {persist_err}")

                    self._customization_cache = data
                    return data
            except Exception as e:
                Backend.logger.error(f"Failed to fetch custom overlay customization: {e}")

            from app.customization import Customization
            data = copy.copy(Customization.reset_state)
            if style and not data.get("preferredStyle"):
                data["preferredStyle"] = style
                try:
                    self.session.post(f"{base_url}/api/raw_config/{custom_id}", json={"customization": data}, timeout=2.0)
                except Exception as persist_err:
                    Backend.logger.warning(f"Failed to persist preferredStyle update: {persist_err}")
            self._customization_cache = data
            return data
            
        response = self.send_command_with_id_and_content("GetCustomization", customOid=customOid)
        if response.status_code == 200:
            return response.json().get('payload')
        return None

    def is_visible(self):
        if self.is_custom_overlay():
            # Standard visibility fallback if stored locally.
            return True
        response = self.send_command_with_id_and_content("GetOverlayVisibility")
        if response.status_code == 200:
            return response.json().get('payload', False)
        return False

    def reset(self, state):
        current = state.get_current_model()
        reset_model = state.get_reset_model()
        
        # Merge reset_model over current_model to preserve unknown keys like "Sets Display"
        new_state = copy.copy(current)
        new_state.update(reset_model)
        
        self.save_model(new_state, False)

    def save(self, state, simple):
        self.save_model(state.get_current_model(), simple)

    def process_response(self, response):
        if response.status_code >= 300:
            logging.warning("response %s: '%s'", response.status_code, response.text)
        else:
            logging.info("response status: %s", response.status_code)
            logging.debug("response message: '%s'", response.text)
        return response

    def get_available_styles(self, oid: str = None) -> list:
        check_oid = oid if oid is not None else self.conf.oid
        if self.is_custom_overlay(check_oid):
            custom_id, _ = self.get_custom_overlay_id(check_oid)
            base_url = EnvVarsManager.get_custom_overlay_url().rstrip('/')
            url = f"{base_url}/api/config/{custom_id}"
            try:
                response = self.session.get(url, timeout=5.0)
                if response.status_code == 200:
                    data = response.json()
                    return data.get('availableStyles', [])
            except Exception as e:
                Backend.logger.error(f"Error fetching available styles from local overlay: {e}")
        return []

    def validate_and_store_model_for_oid(self, oid: str):
        if oid is None or oid.strip() == "":
            logging.debug("empty oid: %s", oid)
            return State.OIDStatus.EMPTY
        
        # First try to fetch the actual layout ID
        self.fetch_and_update_overlay_id(oid)

        result = self.get_current_model(customOid=oid, saveResult=True)
        if result is not None:
            if result.get("game1State") is not None:
                return State.OIDStatus.DEPRECATED
            return State.OIDStatus.VALID
        return State.OIDStatus.INVALID
    
    def fetch_and_update_overlay_id(self, oid: str):
        if self.is_custom_overlay(oid):
            Backend.logger.info('Custom overlay detected, skipping Uno ID fetch')
            return

        Backend.logger.info('Fetching specific overlay ID for oid %s', oid)
        jsonin = {"command": "GetOverlays", "value": ""}
        response = self.do_send_request(oid, jsonin)
        if hasattr(response, 'status_code') and response.status_code == 200:
            payload = response.json().get('payload')
            if payload and isinstance(payload, list) and len(payload) > 0:
                overlay_id = payload[0].get('id')
                if overlay_id:
                    self.conf.id = overlay_id
                    Backend.logger.info('Updated conf.id to %s', overlay_id)
        
    def fetch_output_token(self, oid):
        """
        Fetches the output token associated with the given OID by querying the overlays.uno API.
        """
        if self.is_custom_overlay(oid):
            try:
                Backend.logger.info(f"Fetching local output config for OID: {oid}")
                custom_id, style = self.get_custom_overlay_id(oid)
                base_url = EnvVarsManager.get_custom_overlay_url().rstrip('/')
                url = f"{base_url}/api/config/{custom_id}"
                response = self.session.get(url, timeout=5.0)
                if response.status_code == 200:
                    data = response.json()
                    output_url = data.get('outputUrl')
                    if output_url:
                        if EnvVarsManager.has_custom_overlay_output_url():
                            # Reconstruct output_url to prevent internal proxy hostname/HTTP leakage (Mixed Content block)
                            # Preserve the path from the overlay server (which uses the output key, not the overlay name)
                            output_base_url = EnvVarsManager.get_custom_overlay_output_url().rstrip('/')
                            output_path = urlparse(output_url).path
                            output_url = f"{output_base_url}{output_path}"
                        Backend.logger.info(f"Local output URL found: {output_url}")
                        return output_url
            except Exception as e:
                Backend.logger.error(f"Error fetching local output token: {e}")
            return None

        try:
            Backend.logger.info(f"Fetching output token for OID: {oid}")
            url = f'https://app.overlays.uno/apiv2/controlapps/{oid}'
            # Added a 5.0 second timeout for GET requests
            response = self.session.get(url, timeout=5.0)
            if response.status_code == 200:
                data = response.json()
                output_url = data.get('outputUrl')
                if output_url:
                    match = re.search(r'/output/([^/?]+)', output_url)
                    if match:
                        token = match.group(1)
                        Backend.logger.info(f"Output token found: {token}")
                        return token
            else:
                Backend.logger.warning(f"Failed to fetch output token for OID {oid}: {response.status_code}")
        except requests.exceptions.RequestException as e:
            Backend.logger.error(f"Network error fetching output token: {e}")
        except Exception as e:
            Backend.logger.error(f"Error fetching output token: {e}")
        return None

    def update_local_overlay(self, current_model, force_visibility=None, customization_state=None, show_only_current_set=None):
        try:
            payload = self._build_overlay_payload(
                current_model,
                force_visibility=force_visibility,
                customization_state=customization_state,
                show_only_current_set=show_only_current_set,
            )

            # Prefer WebSocket if connected
            if self._ws_client and self._ws_client.is_connected:
                if self._ws_client.send_state(payload):
                    return

            # Fallback: HTTP POST
            custom_id, _ = self.get_custom_overlay_id()
            base_url = EnvVarsManager.get_custom_overlay_url().rstrip('/')
            url = f"{base_url}/api/state/{custom_id}"
            self.session.post(url, json=payload, timeout=2.0)
        except Exception as e:
            Backend.logger.error(f"Error updating local overlay: {e}")