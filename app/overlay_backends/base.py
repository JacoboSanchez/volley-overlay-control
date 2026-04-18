"""Abstract interface shared by every overlay backend strategy."""

import logging
from abc import ABC, abstractmethod

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
