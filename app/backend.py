import copy
import logging
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from typing import Any

from app.conf import Conf
from app.customization_cache import CustomizationCache
from app.customization_cache_ttl import (
    BACKEND_DEFAULT_TTL_SECONDS,
    customization_cache_ttl_seconds,
)
from app.overlay_backends import (
    LocalOverlayBackend,
    OverlayKind,
    resolve_overlay_kind,
)
from app.overlay_payload import build_overlay_payload
from app.state import State

_CUSTOMIZATION_CACHE_TTL_SECONDS = customization_cache_ttl_seconds(
    default=BACKEND_DEFAULT_TTL_SECONDS,
)

# Warn when a single remote overlay call exceeds this duration. Conservative so
# it only fires on real slowdowns, not on a cold-start connection setup.
_REMOTE_CALL_WARN_MS = 500.0


@contextmanager
def _timed(label: str, logger: logging.Logger) -> Iterator[None]:
    """Log perf_counter-based duration at DEBUG, or WARNING above the threshold."""
    t0 = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        if elapsed_ms > _REMOTE_CALL_WARN_MS:
            logger.warning("%s slow: %.1fms", label, elapsed_ms)
        else:
            logger.debug("%s took %.1fms", label, elapsed_ms)


class Backend:
    """Coordinator that forwards operations to the in-process overlay backend."""

    logger = logging.getLogger(__name__)

    def __init__(self, config: Conf) -> None:
        self.conf = config
        self.executor = ThreadPoolExecutor(max_workers=5)
        self._customization_cache = CustomizationCache(
            _CUSTOMIZATION_CACHE_TTL_SECONDS
        )
        self._rule_overrides_getter: Callable[[], dict[str, Any]] | None = None
        self._overlay = self._create_overlay_backend()

    def set_rule_overrides_getter(
        self, getter: Callable[[], dict[str, Any]] | None
    ) -> None:
        """Register the per-session rule-overrides callable."""
        self._rule_overrides_getter = getter

    def _remember_customization(self, data: dict[str, Any]) -> None:
        """Store a copy of *data* in the cache so callers can't mutate it."""
        self._customization_cache.remember(data)

    def _fresh_customization_cache(self) -> dict[str, Any] | None:
        """Return a fresh copy of the cached customization, or None if stale."""
        return self._customization_cache.fresh()

    def _local_overlay_exists(self, overlay_id: str) -> bool:
        # Prefer the per-user storage key; bare backends fall back to the id.
        from app.overlay import overlay_state_store

        key = self.conf.skey or overlay_id
        return bool(key) and overlay_state_store.overlay_exists(key)

    def _oid_or_default(self, oid: str | None) -> str:
        return oid if oid is not None else (self.conf.oid or "")

    def _resolve_kind(self, oid: str | None = None) -> OverlayKind:
        return resolve_overlay_kind(
            self._oid_or_default(oid), self._local_overlay_exists
        )

    def _create_overlay_backend(
        self,
        oid: str | None = None,
    ) -> LocalOverlayBackend:
        """Instantiate the sole, in-process overlay backend."""
        backend = LocalOverlayBackend(self.conf)
        backend._build_payload = self._build_overlay_payload
        return backend

    def _ensure_overlay_backend(self, oid: str | None = None) -> None:
        """No-op retained for call-site compatibility."""

    # -- Public interface --------------------------------------------------

    def is_custom_overlay(self, oid: str | None = None) -> bool:
        return self._resolve_kind(oid) == OverlayKind.CUSTOM

    def get_custom_overlay_id(
        self,
        oid: str | None = None,
    ) -> tuple[str, str | None]:
        check_oid = self._oid_or_default(oid)
        if self._resolve_kind(check_oid) == OverlayKind.CUSTOM:
            return LocalOverlayBackend.get_overlay_id(check_oid)
        return check_oid, None

    # -- WebSocket lifecycle ----------------------------------------------

    def init_ws_client(self, oid: str | None = None) -> None:
        self._overlay.init_ws_client(self._oid_or_default(oid))

    def close_ws_client(self) -> None:
        self._overlay.close_ws_client()

    def shutdown(self) -> None:
        self._overlay.shutdown()
        executor = getattr(self, "executor", None)
        if executor is None:
            return
        executor.shutdown(wait=True, cancel_futures=False)

    @property
    def ws_connected(self) -> bool:
        return self._overlay.ws_connected

    @property
    def obs_client_count(self) -> int:
        return self._overlay.obs_client_count

    # -- Overlay payload builder ------------------------------------------

    def _build_overlay_payload(
        self,
        current_model: dict[str, Any],
        force_visibility: bool | None = None,
        customization_state: dict[str, Any] | None = None,
        show_only_current_set: bool | None = None,
    ) -> dict[str, Any]:
        """Build the standardized overlay state JSON payload."""
        if customization_state is None:
            cached = self._fresh_customization_cache()
            customization_state = (
                cached
                if cached is not None
                else (self.get_current_customization() or {})
            )
        return build_overlay_payload(
            current_model,
            customization_state,
            conf=self.conf,
            rule_overrides_getter=self._rule_overrides_getter,
            logger=Backend.logger,
            force_visibility=force_visibility,
            show_only_current_set=show_only_current_set,
        )

    # -- Model persistence -------------------------------------------------

    def save_model(
        self,
        current_model: dict[str, Any],
        simple: bool,
    ) -> None:
        Backend.logger.debug("saving model...")
        self._ensure_overlay_backend()
        with _timed("save_model.model", Backend.logger):
            self._overlay.save_model(current_model)

        to_save = copy.copy(current_model)
        if simple:
            to_save = State.simplify_model(to_save)

        def _push() -> None:
            with _timed("save_model.push", Backend.logger):
                self._overlay.push_model_update(
                    current_model,
                    to_save,
                    show_only_current_set=simple,
                )

        if self.conf.multithread:
            self.executor.submit(_push)
        else:
            _push()

    def reduce_games_to_one(self) -> None:
        self._ensure_overlay_backend()
        self._overlay.reduce_games_to_one()

    def save_json_model(self, to_save: dict[str, Any]) -> None:
        Backend.logger.debug("saving JSON model...")
        self._ensure_overlay_backend()
        self._overlay.send_json_model(to_save)

    def save_json_customization(self, to_save: dict[str, Any]) -> None:
        Backend.logger.debug("saving JSON customization...")
        self._ensure_overlay_backend()
        self._remember_customization(to_save)
        self._overlay.save_customization(to_save)

        def get_model() -> dict[str, Any] | None:
            return self.get_current_model(self.conf.oid)

        if self.conf.multithread:
            self.executor.submit(
                self._overlay.on_customization_saved,
                get_model,
                to_save,
            )
        else:
            self._overlay.on_customization_saved(get_model, to_save)

    def change_overlay_visibility(self, show: bool) -> None:
        Backend.logger.debug("changing overlay visibility, show: %s", show)
        self._ensure_overlay_backend()
        self._overlay.change_visibility_with_fallback(
            show,
            lambda: self.get_current_model(self.conf.oid),
        )

    # -- Model/customization retrieval ------------------------------------

    def get_current_model(
        self,
        customOid: str | None = None,
        saveResult: bool = False,
    ) -> dict[str, Any] | None:
        oid = customOid if customOid is not None else self.conf.oid
        Backend.logger.debug("getting state for oid %s", oid)
        with _timed("get_current_model", Backend.logger):
            self._ensure_overlay_backend(oid)
            return self._overlay.get_model(oid=oid, save_result=saveResult)

    def get_current_customization(
        self,
        customOid: str | None = None,
    ) -> dict[str, Any] | None:
        Backend.logger.debug("getting customization")
        with _timed("get_current_customization", Backend.logger):
            oid = customOid if customOid is not None else self.conf.oid
            self._ensure_overlay_backend(oid)
            data = self._overlay.get_customization(oid=oid)
            if data is not None:
                self._remember_customization(data)
            return data

    def is_visible(self) -> bool:
        self._ensure_overlay_backend()
        return self._overlay.is_visible()

    def get_available_styles(
        self,
        oid: str | None = None,
    ) -> list[str]:
        check_oid = self._oid_or_default(oid)
        self._ensure_overlay_backend(check_oid)
        return self._overlay.get_available_styles(check_oid)

    def get_style_capabilities(
        self,
        oid: str | None = None,
    ) -> dict[str, Any]:
        check_oid = self._oid_or_default(oid)
        self._ensure_overlay_backend(check_oid)
        return self._overlay.get_style_capabilities(check_oid)

    # -- OID validation / output token ------------------------------------

    def validate_and_store_model_for_oid(self, oid: str) -> State.OIDStatus:
        if not oid or not oid.strip():
            return State.OIDStatus.EMPTY
        self._ensure_overlay_backend(oid)
        return self._overlay.validate_oid(oid)

    def fetch_and_update_overlay_id(self, oid: str) -> None:
        self._ensure_overlay_backend(oid)
        self._overlay.fetch_and_update_overlay_id(oid)

    def fetch_output_token(self, oid: str) -> str | None:
        self._ensure_overlay_backend(oid)
        return self._overlay.fetch_output_token(oid)

    # -- High-level helpers ------------------------------------------------

    def reset(self, state: State) -> None:
        current = state.get_current_model()
        reset_model = state.get_reset_model()
        new_state = copy.copy(current)
        new_state.update(reset_model)
        self.save_model(new_state, False)

    def save(self, state: State, simple: bool) -> None:
        self.save_model(state.get_current_model(), simple)

    def update_local_overlay(
        self,
        current_model: dict[str, Any],
        force_visibility: bool | None = None,
        customization_state: dict[str, Any] | None = None,
        show_only_current_set: bool | None = None,
    ) -> None:
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
