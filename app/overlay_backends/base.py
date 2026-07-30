"""Abstract interface shared by every overlay backend strategy."""

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from app.overlay_backends.utils import split_custom_oid
from app.state import State

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.conf import Conf

logger = logging.getLogger(__name__)


class CustomOidMixin:
    """Shared OID parsing helpers for the overlay backend.

    Accepts the ``id[/style]`` (and legacy ``C-id[/style]``) syntax and
    exposes the base-id / style accessors used by :class:`LocalOverlayBackend`.
    """

    # Supplied by the concrete backend this mixin is combined with —
    # ``LocalOverlayBackend.__init__`` assigns it. Declared here (annotation
    # only, no class attribute created) so the ``self.conf`` reads below
    # type-check instead of relying on unchecked function bodies.
    conf: "Conf"

    @staticmethod
    def get_overlay_id(oid: str | None) -> tuple[str, str | None]:
        """Extract base_id and optional style from a custom OID."""
        return split_custom_oid(oid)

    def _custom_id(self, oid: str | None = None) -> str:
        check_oid = oid if oid is not None else self.conf.oid
        cid, _ = split_custom_oid(check_oid)
        return cid

    def _style(self, oid: str | None = None) -> str | None:
        check_oid = oid if oid is not None else self.conf.oid
        _, style = split_custom_oid(check_oid)
        return style


class OverlayBackend(ABC):
    """Abstract interface for overlay communication."""

    @abstractmethod
    def save_model(self, current_model: dict[str, Any]) -> None:
        """Persist the raw game model to the overlay backend."""

    @abstractmethod
    def save_customization(self, data: dict[str, Any]) -> None:
        """Persist customization data."""

    @abstractmethod
    def change_visibility(self, show: bool) -> None:
        """Toggle overlay visibility."""

    @abstractmethod
    def get_model(
        self,
        oid: str | None = None,
        save_result: bool = False,
    ) -> dict[str, Any] | None:
        """Retrieve the current raw game model."""

    @abstractmethod
    def get_customization(
        self,
        oid: str | None = None,
    ) -> dict[str, Any] | None:
        """Retrieve the current customization dict."""

    @abstractmethod
    def is_visible(self) -> bool:
        """Return whether the overlay is currently visible."""

    @abstractmethod
    def get_available_styles(
        self,
        oid: str | None = None,
    ) -> list[str]:
        """Return list of available overlay styles."""

    def get_style_capabilities(
        self,
        oid: str | None = None,
    ) -> dict[str, Any]:
        """Per-style UI capability flags (theme / vertical-anchor support)."""
        return {}

    @abstractmethod
    def fetch_output_token(self, oid: str | None = None) -> str | None:
        """Fetch the output URL or token for this overlay."""

    @abstractmethod
    def validate_oid(self, oid: str) -> State.OIDStatus:
        """Validate the OID and return a status."""

    @abstractmethod
    def fetch_and_update_overlay_id(self, oid: str) -> None:
        """Fetch the specific overlay layout ID from the provider."""

    @abstractmethod
    def send_overlay_state(
        self,
        payload: dict[str, Any],
        force_visibility: bool | None = None,
        customization_state: dict[str, Any] | None = None,
        show_only_current_set: bool | None = None,
    ) -> None:
        """Push a full overlay state update to connected displays."""

    @abstractmethod
    def send_json_model(self, to_save: dict[str, Any]) -> None:
        """Send a partial model update to the overlay provider."""

    @abstractmethod
    def reduce_games_to_one(self) -> None:
        """Reset scores of sets 2-5 to zero."""

    def push_model_update(
        self,
        current_model: dict[str, Any],
        to_save: dict[str, Any],
        show_only_current_set: bool | None = None,
    ) -> None:
        """Push a model update using the backend-appropriate mechanism.

        :class:`LocalOverlayBackend` overrides this to send a full overlay
        state payload to the in-process display hub.
        """
        self.send_json_model(to_save)

    def on_customization_saved(
        self,
        get_model: Callable[[], dict[str, Any] | None],
        customization: dict[str, Any],
    ) -> None:
        """Hook called after customization is persisted (no-op by default).

        *get_model* is a callable returning the current model dict.
        """

    def change_visibility_with_fallback(
        self,
        show: bool,
        get_model: Callable[[], dict[str, Any] | None] | None = None,
    ) -> None:
        """Toggle visibility with an optional HTTP fallback.

        *get_model* is a callable returning the current model dict (called
        lazily only when the fallback path is needed).  Default
        implementation delegates to ``change_visibility``.
        """
        self.change_visibility(show)

    def init_ws_client(self, oid: str | None = None) -> None:
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
