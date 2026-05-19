"""Shared TTL for customization fetch caches (GameService + Backend).

Both caches read the same ``CUSTOMIZATION_CACHE_TTL_SECONDS`` env var so an
operator has a single knob to tune them in lockstep, but their *defaults*
differ on purpose: the GameService cache shields a short request/response
loop where staleness is cheap (5s), while Backend's cache fronts outbound
HTTP to the overlay server where the round-trip cost favours a longer
window (60s). Callers pass their own ``default`` to declare intent; the
env var, when set, still overrides both.
"""

from __future__ import annotations

from app.env_vars_manager import EnvVarsManager

GAME_SERVICE_DEFAULT_TTL_SECONDS = 5.0
BACKEND_DEFAULT_TTL_SECONDS = 60.0


def customization_cache_ttl_seconds(
    default: float = GAME_SERVICE_DEFAULT_TTL_SECONDS,
) -> float:
    """Return the customization cache TTL from env or *default*."""
    raw = EnvVarsManager.get_env_var("CUSTOMIZATION_CACHE_TTL_SECONDS", None)
    if raw is None:
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default
