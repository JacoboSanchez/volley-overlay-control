import copy
import logging
from concurrent.futures import ThreadPoolExecutor

from app.state import State
from app.overlay_backends import (
    UnoOverlayBackend,
    LocalOverlayBackend,
    is_custom_overlay,
)

import requests


class Backend:
    """Coordinator that delegates overlay communication to the right strategy.

    Instantiates either a ``UnoOverlayBackend`` or ``LocalOverlayBackend``
    based on the OID prefix and forwards all overlay-specific operations.
    """

    logger = logging.getLogger(__name__)

    def __init__(self, config):
        self.conf = config
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': self.conf.rest_user_agent,
            'Content-Type': 'application/json',
            'Accept': 'application/json, text/plain, */*'
        })
        self.executor = ThreadPoolExecutor(max_workers=5)
        self._customization_cache = None
        self._overlay = self._create_overlay_backend()

    def _create_overlay_backend(self, oid=None):
        """Instantiate the right overlay backend for the given OID."""
        check_oid = oid if oid is not None else self.conf.oid
        if is_custom_overlay(check_oid):
            from app.overlay import overlay_state_store, obs_broadcast_hub
            backend = LocalOverlayBackend(self.conf, overlay_state_store, obs_broadcast_hub)
            backend._build_payload = self._build_overlay_payload
            return backend
        return UnoOverlayBackend(self.conf, self.session)

    def _ensure_overlay_backend(self, oid=None):
        """Re-create the overlay backend if the OID type changed."""
        check_oid = oid if oid is not None else self.conf.oid
        is_custom = is_custom_overlay(check_oid)
        if is_custom != self._overlay.is_custom:
            self._overlay.close_ws_client()
            self._overlay = self._create_overlay_backend(check_oid)

    # -- Public interface (used by GameManager, GameSession, routes, GUI) ----

    def is_custom_overlay(self, oid=None):
        check_oid = oid if oid is not None else self.conf.oid
        return is_custom_overlay(check_oid)

    def get_custom_overlay_id(self, oid=None):
        check_oid = oid if oid is not None else self.conf.oid
        if is_custom_overlay(check_oid):
            return LocalOverlayBackend.get_overlay_id(check_oid)
        return check_oid, None

    # -- WebSocket lifecycle (delegated) ------------------------------------

    def init_ws_client(self, oid=None):
        check_oid = oid if oid is not None else self.conf.oid
        if not is_custom_overlay(check_oid):
            return
        self._ensure_overlay_backend(check_oid)
        self._overlay.init_ws_client(check_oid)

    def close_ws_client(self):
        self._overlay.close_ws_client()

    def shutdown(self):
        self._overlay.shutdown()
        if hasattr(self, 'executor') and self.executor:
            self.executor.shutdown(wait=False)

    @property
    def ws_connected(self):
        return self._overlay.ws_connected

    @property
    def obs_client_count(self):
        return self._overlay.obs_client_count

    # -- Overlay payload builder -------------------------------------------

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

    # -- Model persistence --------------------------------------------------

    def save_model(self, current_model, simple):
        Backend.logger.info('saving model...')
        self._ensure_overlay_backend()
        self._overlay.save_model(current_model)

        to_save = copy.copy(current_model)
        if simple:
            to_save = State.simplify_model(to_save)

        if self.conf.id == State.CHAMPIONSHIP_LAYOUT_ID:
            to_save["Sets Display"] = str(to_save.get(State.CURRENT_SET_INT, "1"))

        if self.conf.multithread:
            self.executor.submit(
                self._overlay.push_model_update, current_model, to_save,
                show_only_current_set=simple,
            )
        else:
            self._overlay.push_model_update(
                current_model, to_save, show_only_current_set=simple,
            )
        Backend.logger.info('saved')

    def reduce_games_to_one(self):
        self._ensure_overlay_backend()
        self._overlay.reduce_games_to_one()

    def save_json_model(self, to_save):
        Backend.logger.info('saving JSON model...')
        self._ensure_overlay_backend()
        self._overlay.send_json_model(to_save)

    def save_json_customization(self, to_save):
        Backend.logger.info('saving JSON customization...')
        self._ensure_overlay_backend()
        self._customization_cache = to_save

        self._overlay.save_customization(to_save)

        get_model = lambda: self.get_current_model(self.conf.oid)
        if self.conf.multithread:
            self.executor.submit(
                self._overlay.on_customization_saved, get_model, to_save,
            )
        else:
            self._overlay.on_customization_saved(get_model, to_save)

    def change_overlay_visibility(self, show):
        Backend.logger.info('changing overlay visibility, show: %s', show)
        self._ensure_overlay_backend()
        self._overlay.change_visibility_with_fallback(
            show, lambda: self.get_current_model(self.conf.oid),
        )

    # -- Model/customization retrieval --------------------------------------

    def get_current_model(self, customOid=None, saveResult=False):
        oid = customOid if customOid is not None else self.conf.oid
        Backend.logger.info('getting state for oid %s', oid)
        self._ensure_overlay_backend(oid)
        return self._overlay.get_model(oid=oid, save_result=saveResult)

    def get_current_customization(self, customOid=None):
        Backend.logger.info('getting customization')
        oid = customOid if customOid is not None else self.conf.oid
        self._ensure_overlay_backend(oid)
        data = self._overlay.get_customization(oid=oid)
        if data is not None:
            self._customization_cache = data
        return data

    def is_visible(self):
        self._ensure_overlay_backend()
        return self._overlay.is_visible()

    def get_available_styles(self, oid: str = None) -> list:
        check_oid = oid if oid is not None else self.conf.oid
        self._ensure_overlay_backend(check_oid)
        return self._overlay.get_available_styles(check_oid)

    # -- OID validation / output token -------------------------------------

    def validate_and_store_model_for_oid(self, oid: str):
        if oid is None or oid.strip() == "":
            return State.OIDStatus.EMPTY
        self._ensure_overlay_backend(oid)
        return self._overlay.validate_oid(oid)

    def fetch_and_update_overlay_id(self, oid: str):
        self._ensure_overlay_backend(oid)
        self._overlay.fetch_and_update_overlay_id(oid)

    def fetch_output_token(self, oid):
        self._ensure_overlay_backend(oid)
        return self._overlay.fetch_output_token(oid)

    # -- High-level helpers ------------------------------------------------

    def reset(self, state):
        current = state.get_current_model()
        reset_model = state.get_reset_model()
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

    def update_local_overlay(self, current_model, force_visibility=None,
                             customization_state=None, show_only_current_set=None):
        try:
            payload = self._build_overlay_payload(
                current_model,
                force_visibility=force_visibility,
                customization_state=customization_state,
                show_only_current_set=show_only_current_set,
            )
            self._overlay.send_overlay_state(payload)
        except Exception as e:
            Backend.logger.error("Error updating local overlay: %s", e)

    # -- Uno-specific pass-through (used by legacy code paths) ----

    def send_command_with_value(self, command, value="", customOid=None):
        """Send a value-type command to the Uno API."""
        if not self._overlay.is_custom:
            return self._overlay._send_command_with_value(command, value, customOid)
        return None

    def send_command_with_id_and_content(self, command, content="", customOid=None):
        """Send a command with id+content to the Uno API."""
        if not self._overlay.is_custom:
            return self._overlay._send_command(command, content, customOid)
        return None

    def do_send_request(self, oid, jsonin):
        """Direct request to the Uno API (legacy compatibility)."""
        if is_custom_overlay(oid):
            from app.overlay_backends import _mock_response
            return _mock_response(200)

        if isinstance(self._overlay, UnoOverlayBackend):
            return self._overlay._do_request(oid, jsonin)

        from app.overlay_backends import _mock_response
        return _mock_response(200)
