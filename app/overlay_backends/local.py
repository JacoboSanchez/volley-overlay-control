"""In-process overlay backend — no external server required."""

import copy
import logging

from app.env_vars_manager import EnvVarsManager
from app.state import State

from app.overlay_backends.base import OverlayBackend
from app.overlay_backends.utils import split_custom_oid

logger = logging.getLogger(__name__)


class LocalOverlayBackend(OverlayBackend):
    """In-process overlay backend — no external server needed.

    Manages overlay state directly via the ``app.overlay`` package instead
    of sending HTTP requests or WebSocket messages to an external server.
    """

    def __init__(self, conf):
        self.conf = conf
        # Build overlay payload callback — set by Backend after construction
        self._build_payload = None

    # Backwards-compatible static helper (used elsewhere in the codebase).
    @staticmethod
    def get_overlay_id(oid: str):
        """Extract base_id and optional style from a custom OID."""
        return split_custom_oid(oid)

    def _custom_id(self, oid=None):
        check_oid = oid if oid is not None else self.conf.oid
        cid, _ = split_custom_oid(check_oid)
        return cid

    def _style(self, oid=None):
        check_oid = oid if oid is not None else self.conf.oid
        _, style = split_custom_oid(check_oid)
        return style

    def _store(self):
        from app.overlay import overlay_state_store
        return overlay_state_store

    def _broadcast(self):
        from app.overlay import obs_broadcast_hub
        return obs_broadcast_hub

    @property
    def is_custom(self) -> bool:
        return True

    @property
    def obs_client_count(self) -> int:
        return self._broadcast().get_client_count(self._custom_id())

    # -- OverlayBackend interface --

    def save_model(self, current_model: dict) -> None:
        custom_id = self._custom_id()
        self._store().ensure_overlay(custom_id)
        self._store().set_raw_config(custom_id, model=current_model)

    def save_customization(self, data: dict) -> None:
        custom_id = self._custom_id()
        self._store().ensure_overlay(custom_id)
        self._store().set_raw_config(custom_id, customization=data)

    def change_visibility(self, show: bool) -> None:
        custom_id = self._custom_id()
        self._store().ensure_overlay(custom_id)
        self._store().set_visibility(custom_id, show)

    def get_model(self, oid: str = None, save_result: bool = False) -> dict | None:
        custom_id = self._custom_id(oid)
        self._store().ensure_overlay(custom_id)
        raw = self._store().get_raw_config(custom_id)
        model = raw.get("model", {})
        return model if model else State().get_reset_model()

    def _get_default_customization(self, style, custom_id):
        """Return a default customization dict, persisting preferredStyle."""
        from app.customization import Customization
        data = copy.copy(Customization.reset_state)
        if style:
            data["preferredStyle"] = style
        self._store().set_raw_config(custom_id, customization=data)
        return data

    def get_customization(self, oid: str = None) -> dict | None:
        check_oid = oid if oid is not None else self.conf.oid
        custom_id = self._custom_id(check_oid)
        style = self._style(check_oid)

        self._store().ensure_overlay(custom_id)
        raw = self._store().get_raw_config(custom_id)
        data = raw.get("customization", {})

        if not data:
            return self._get_default_customization(style, custom_id)
        if style and not data.get("preferredStyle"):
            data["preferredStyle"] = style
            self._store().set_raw_config(custom_id, customization=data)
        return data

    def is_visible(self) -> bool:
        custom_id = self._custom_id()
        self._store().ensure_overlay(custom_id)
        state = self._store().get_state(custom_id)
        overlay_control = state.get("overlay_control") or {}
        return overlay_control.get("show_main_scoreboard") not in (
            False, "false", 0, "0",
        )

    def get_available_styles(self, oid: str = None) -> list:
        return self._store().get_available_styles_list()

    def fetch_output_token(self, oid: str = None) -> str | None:
        from app.overlay.state_store import OverlayStateStore
        custom_id = self._custom_id(oid)
        output_key = OverlayStateStore.get_output_key(custom_id)
        public_url = EnvVarsManager.get_env_var('OVERLAY_PUBLIC_URL', None)
        if public_url:
            base = public_url.rstrip('/')
        else:
            port = EnvVarsManager.get_env_var('APP_PORT', '8080')
            base = f"http://localhost:{port}"
        return f"{base}/overlay/{output_key}"

    def validate_oid(self, oid: str) -> State.OIDStatus:
        custom_id = self._custom_id(oid)
        self._store().ensure_overlay(custom_id)
        return State.OIDStatus.VALID

    def fetch_and_update_overlay_id(self, oid: str) -> None:
        logger.info('Local overlay detected, skipping ID fetch')

    def send_overlay_state(self, payload, **kwargs) -> None:
        """Push state update into the in-process state store."""
        custom_id = self._custom_id()
        self._store().ensure_overlay(custom_id)
        self._store().update_state_sync(custom_id, payload)

    def send_json_model(self, to_save: dict) -> None:
        pass  # Local overlays don't use Uno's SetOverlayContent

    def reduce_games_to_one(self) -> None:
        pass  # Local overlays don't use Uno's SetOverlayContent

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
        if self._build_payload and get_model:
            current_model = get_model()
            if current_model:
                payload = self._build_payload(
                    current_model, force_visibility=show,
                )
                self.send_overlay_state(payload)

    # WebSocket lifecycle not needed — no external WS connection
    def init_ws_client(self, oid=None):
        pass

    def close_ws_client(self):
        pass

    def shutdown(self):
        pass
