"""Shared TTL for customization fetch caches (GameService + Backend)."""

from __future__ import annotations

from app.env_vars_manager import EnvVarsManager

_DEFAULT_TTL_SECONDS = 5.0


def customization_cache_ttl_seconds() -> float:
    """Return the customization cache TTL from env or the default."""
    raw = EnvVarsManager.get_env_var("CUSTOMIZATION_CACHE_TTL_SECONDS", None)
    if raw is None:
        return _DEFAULT_TTL_SECONDS
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return _DEFAULT_TTL_SECONDS
    return value if value > 0 else _DEFAULT_TTL_SECONDS
