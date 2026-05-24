"""Runtime app-level configuration exposed to the frontend.

The application title is configurable via the ``APP_TITLE`` environment
variable; the stale-set threshold (operator-facing "match looks
abandoned" prompt) is configurable via ``STALE_SET_THRESHOLD_MINUTES``.
Both are consumed by the SPA (via ``GET /api/v1/app-config``); the
title is also injected into the served ``index.html`` and the PWA
manifest.
"""

import logging

from app.env_vars_manager import EnvVarsManager

logger = logging.getLogger(__name__)

DEFAULT_APP_TITLE = "Volley Scoreboard"

# Default minutes a single set may be live before the abandoned-match
# prompt fires on the next control-UI load. ``0`` disables the prompt.
DEFAULT_STALE_SET_THRESHOLD_MINUTES = 60


def get_app_title() -> str:
    """Return the configured application title, falling back to the default."""
    value = EnvVarsManager.get_env_var("APP_TITLE", DEFAULT_APP_TITLE)
    if isinstance(value, str):
        value = value.strip()
    return value or DEFAULT_APP_TITLE


def get_stale_set_threshold_minutes() -> int:
    """Return the configured stale-set threshold in minutes.

    Falls back to :data:`DEFAULT_STALE_SET_THRESHOLD_MINUTES` (60) when
    the env var is unset, empty, or non-numeric. Negative values clamp
    to ``0`` so callers can safely treat any non-positive value as
    "prompt disabled".
    """
    raw = EnvVarsManager.get_env_var(
        "STALE_SET_THRESHOLD_MINUTES", DEFAULT_STALE_SET_THRESHOLD_MINUTES,
    )
    try:
        value = int(raw)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid STALE_SET_THRESHOLD_MINUTES=%r; falling back to %d.",
            raw, DEFAULT_STALE_SET_THRESHOLD_MINUTES,
        )
        return DEFAULT_STALE_SET_THRESHOLD_MINUTES
    return max(0, value)
