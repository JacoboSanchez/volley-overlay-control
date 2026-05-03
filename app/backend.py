import copy
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.customization_cache import CustomizationCache
from app.env_vars_manager import EnvVarsManager
from app.overlay_backends import (
    CustomOverlayBackend,
    LocalOverlayBackend,
    OverlayKind,
    UnoOverlayBackend,
    resolve_overlay_kind,
)
from app.state import State

# TTL for the in-memory customization cache. Overlay customization (team names,
# colors, geometry) rarely changes during a match, but if an operator edits it
# in another tab or via the admin panel a stale cache would delay propagation
# for the duration of the match. 60s balances freshness against the cost of
# extra GET round-trips on every save.
_CUSTOMIZATION_CACHE_TTL_SECONDS = 60.0

# Warn when a single remote overlay call exceeds this duration. Conservative so
# it only fires on real slowdowns, not on a cold-start connection setup.
_REMOTE_CALL_WARN_MS = 500.0


@contextmanager
def _timed(label: str, logger: logging.Logger):
    """Log perf_counter-based duration at DEBUG, or WARNING above the threshold."""
    t0 = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        if elapsed_ms > _REMOTE_CALL_WARN_MS:
            logger.warning('%s slow: %.1fms', label, elapsed_ms)
        else:
            logger.debug('%s took %.1fms', label, elapsed_ms)


class Backend:
    """Coordinator that delegates overlay communication to the right strategy.

    Instantiates either a ``UnoOverlayBackend`` or ``CustomOverlayBackend``
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
        # Pool sized for ThreadPoolExecutor (max_workers=5) plus the foreground
        # request thread, with headroom. Retry covers transient 5xx/connection
        # hiccups from the overlay server without masking real failures — the
        # short per-call timeouts (2-5 s) keep the worst case bounded.
        _adapter = HTTPAdapter(
            pool_connections=10,
            pool_maxsize=20,
            max_retries=Retry(
                total=2,
                backoff_factor=0.3,
                status_forcelist=(502, 503, 504),
                allowed_methods=frozenset(["GET", "PUT", "POST"]),
                raise_on_status=False,
            ),
        )
        self.session.mount("http://", _adapter)
        self.session.mount("https://", _adapter)
        self.executor = ThreadPoolExecutor(max_workers=5)
        self._customization_cache = CustomizationCache(
            _CUSTOMIZATION_CACHE_TTL_SECONDS
        )
        self._overlay = self._create_overlay_backend()

    def _remember_customization(self, data):
        """Store a copy of *data* in the cache so callers can't mutate it."""
        self._customization_cache.remember(data)

    def _fresh_customization_cache(self):
        """Return a fresh copy of the cached customization, or None if stale."""
        return self._customization_cache.fresh()

    @staticmethod
    def _local_overlay_exists(overlay_id: str) -> bool:
        from app.overlay import overlay_state_store
        return bool(overlay_id) and overlay_state_store.overlay_exists(overlay_id)

    def _resolve_kind(self, oid=None) -> OverlayKind:
        check_oid = oid if oid is not None else self.conf.oid
        return resolve_overlay_kind(check_oid, self._local_overlay_exists)

    def _create_overlay_backend(self, oid=None):
        """Instantiate the right overlay backend for the given OID.

        Custom overlays use ``LocalOverlayBackend`` (in-process) by default;
        when ``APP_CUSTOM_OVERLAY_URL`` is set, ``CustomOverlayBackend``
        (external server) is used instead. Anything else (including OIDs
        that fail to resolve) falls back to ``UnoOverlayBackend`` so that
        validation can later report INVALID via the cloud REST API.
        """
        if self._resolve_kind(oid) == OverlayKind.CUSTOM:
            external_url = EnvVarsManager.get_env_var(
                'APP_CUSTOM_OVERLAY_URL', None
            )
            if external_url:
                backend = CustomOverlayBackend(self.conf, self.session)
            else:
                backend = LocalOverlayBackend(self.conf)
            backend._build_payload = self._build_overlay_payload
            return backend
        return UnoOverlayBackend(self.conf, self.session)

    def _ensure_overlay_backend(self, oid=None):
        """Re-create the overlay backend if the OID type changed."""
        is_custom = self._resolve_kind(oid) == OverlayKind.CUSTOM
        if is_custom != self._overlay.is_custom:
            self._overlay.close_ws_client()
            self._overlay = self._create_overlay_backend(oid)

    # -- Public interface (used by GameManager, GameSession, routes, GUI) ----

    def is_custom_overlay(self, oid=None):
        return self._resolve_kind(oid) == OverlayKind.CUSTOM

    def get_custom_overlay_id(self, oid=None):
        check_oid = oid if oid is not None else self.conf.oid
        if self._resolve_kind(check_oid) == OverlayKind.CUSTOM:
            # Both LocalOverlayBackend and CustomOverlayBackend share
            # the same static get_overlay_id parser.
            return LocalOverlayBackend.get_overlay_id(check_oid)
        return check_oid, None

    # -- WebSocket lifecycle (delegated) ------------------------------------

    def init_ws_client(self, oid=None):
        check_oid = oid if oid is not None else self.conf.oid
        if self._resolve_kind(check_oid) != OverlayKind.CUSTOM:
            return
        self._ensure_overlay_backend(check_oid)
        self._overlay.init_ws_client(check_oid)

    def close_ws_client(self):
        self._overlay.close_ws_client()

    def shutdown(self):
        # Close the WebSocket first so no new tasks are submitted that would
        # race with the executor drain below.
        self._overlay.shutdown()
        executor = getattr(self, 'executor', None)
        if executor is None:
            return
        # wait=True so in-flight overlay saves aren't abandoned mid-request.
        # cancel_futures=False preserves the queued tasks (queued saves will
        # run before the executor finally exits).
        executor.shutdown(wait=True, cancel_futures=False)

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
            cached = self._fresh_customization_cache()
            customization_state = (
                cached if cached is not None
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
        Backend.logger.debug('saving model...')
        self._ensure_overlay_backend()
        with _timed('save_model.model', Backend.logger):
            self._overlay.save_model(current_model)

        to_save = copy.copy(current_model)
        if simple:
            to_save = State.simplify_model(to_save)

        if self.conf.id == State.CHAMPIONSHIP_LAYOUT_ID:
            to_save["Sets Display"] = str(to_save.get(State.CURRENT_SET_INT, "1"))

        # Wrap the push inside the callable so the timing span runs where the
        # call actually executes — either inline (sync) or on the executor
        # thread (multithread). Otherwise the multithread branch would only
        # measure `executor.submit` (microseconds) and the WARNING threshold
        # would never fire even on a genuinely slow remote save.
        def _push():
            with _timed('save_model.push', Backend.logger):
                self._overlay.push_model_update(
                    current_model, to_save, show_only_current_set=simple,
                )

        if self.conf.multithread:
            self.executor.submit(_push)
        else:
            _push()

    def reduce_games_to_one(self):
        self._ensure_overlay_backend()
        self._overlay.reduce_games_to_one()

    def save_json_model(self, to_save):
        Backend.logger.debug('saving JSON model...')
        self._ensure_overlay_backend()
        self._overlay.send_json_model(to_save)

    def save_json_customization(self, to_save):
        Backend.logger.debug('saving JSON customization...')
        self._ensure_overlay_backend()
        self._remember_customization(to_save)

        self._overlay.save_customization(to_save)

        def get_model():
            return self.get_current_model(self.conf.oid)

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
        Backend.logger.debug('getting state for oid %s', oid)
        with _timed('get_current_model', Backend.logger):
            self._ensure_overlay_backend(oid)
            return self._overlay.get_model(oid=oid, save_result=saveResult)

    def get_current_customization(self, customOid=None):
        Backend.logger.debug('getting customization')
        with _timed('get_current_customization', Backend.logger):
            oid = customOid if customOid is not None else self.conf.oid
            self._ensure_overlay_backend(oid)
            data = self._overlay.get_customization(oid=oid)
            if data is not None:
                self._remember_customization(data)
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
        if response.status_code >= 400:
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
        except Exception:
            Backend.logger.exception("Error updating local overlay")

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
        from app.overlay_backends import _mock_response
        if self._resolve_kind(oid) != OverlayKind.UNO:
            return _mock_response(200)

        if isinstance(self._overlay, UnoOverlayBackend):
            return self._overlay._do_request(oid, jsonin)

        return _mock_response(200)
