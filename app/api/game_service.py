"""Stable facade over focused game services."""

import time as time

from app.api.game_actions import GameActions
from app.api.game_customization_service import GameCustomizationService
from app.api.game_display_service import GameDisplayService
from app.api.game_rapid_pair import RAPID_PAIR_WINDOW_S as RAPID_PAIR_WINDOW_S
from app.api.game_state_presenter import GameStatePresenter
from app.customization_cache_ttl import customization_cache_ttl_seconds

CUSTOMIZATION_CACHE_TTL_SECONDS = customization_cache_ttl_seconds()


class GameService(
    GameActions,
    GameDisplayService,
    GameCustomizationService,
    GameStatePresenter,
):
    """Stateless compatibility facade used by routes and integrations."""
