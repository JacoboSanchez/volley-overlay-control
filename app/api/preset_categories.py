"""Six categories the operator picks from when saving a preset.

The React control panel groups its customization fields into six
buckets: each team's *name* and *colour/logo* (so ``team1_name`` /
``team1_color`` / ``team2_name`` / ``team2_color``), the overlay
``position`` block, and the broader ``style`` (palette + preferred
template + cosmetic toggles). Mapping is one-to-many — every
``ALLOWED_CUSTOMIZATION_KEYS`` member belongs to exactly one
category, so the React side can render category chips without the
backend having to ship a per-key tagging table.

This module is the single source of truth for that mapping. The
backend uses it to:

* derive a record's ``categories`` field at save time from the keys
  in its ``values`` payload, so the field can never drift out of sync
  with the actual content.
* drop unknown keys before persistence — anything outside
  ``ALLOWED_CUSTOMIZATION_KEYS`` is filtered out, not stored.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from app.api.schemas import ALLOWED_CUSTOMIZATION_KEYS

# Ordered so list and chip rendering stays stable across requests.
CATEGORY_ORDER: tuple[str, ...] = (
    "team1_name",
    "team1_color",
    "team2_name",
    "team2_color",
    "position",
    "style",
)


# Each category owns a subset of ``ALLOWED_CUSTOMIZATION_KEYS``. The
# union must equal the allow-list — otherwise some keys would silently
# fall outside the category model and the operator would not be able
# to save them. ``_validate_partition`` enforces that at import time.
_KEYS_BY_CATEGORY: dict[str, tuple[str, ...]] = {
    "team1_name": ("Team 1 Name", "Team 1 Text Name"),
    "team1_color": ("Team 1 Color", "Team 1 Text Color", "Team 1 Logo"),
    "team2_name": ("Team 2 Name", "Team 2 Text Name"),
    "team2_color": ("Team 2 Color", "Team 2 Text Color", "Team 2 Logo"),
    "position": ("Height", "Width", "Left-Right", "Up-Down", "Scale", "Margin"),
    "style": (
        "preferredStyle",
        "overlayTheme",
        "verticalAnchor",
        "Logos",
        "Gradient",
        "Color 1",
        "Color 2",
        "Text Color 1",
        "Text Color 2",
    ),
}


# Allow-listed customization keys that intentionally do NOT belong to
# any preset category — they're per-operator/per-session knobs whose
# round-trip through a saved preset would surprise the operator that
# loads it. ``locale`` (the operator's UI language, pushed onto the
# overlay so OBS browser sources follow language changes) is the only
# such key today.
_NON_PRESET_KEYS: frozenset[str] = frozenset({"locale"})


def _validate_partition() -> dict[str, str]:
    """Build (and check) the reverse ``key → category`` map.

    Raises ``RuntimeError`` if the categories don't partition
    ``ALLOWED_CUSTOMIZATION_KEYS`` exactly (minus the explicit
    :data:`_NON_PRESET_KEYS` exemption). The check runs once at import
    time, so adding a new allow-listed key without slotting it into a
    category — or into the non-preset opt-out — fails fast in the
    test suite rather than silently producing un-categorised presets
    in production.
    """
    reverse: dict[str, str] = {}
    for cat, keys in _KEYS_BY_CATEGORY.items():
        for key in keys:
            if key in reverse:
                raise RuntimeError(
                    f"Customization key '{key}' is in both "
                    f"'{reverse[key]}' and '{cat}' categories.",
                )
            if key in _NON_PRESET_KEYS:
                raise RuntimeError(
                    f"Customization key '{key}' is both in category "
                    f"'{cat}' and in ``_NON_PRESET_KEYS``.",
                )
            reverse[key] = cat
    leftover = set(ALLOWED_CUSTOMIZATION_KEYS) - set(reverse) - _NON_PRESET_KEYS
    if leftover:
        raise RuntimeError(
            "ALLOWED_CUSTOMIZATION_KEYS members not assigned to any "
            f"preset category: {sorted(leftover)}. Either slot them "
            "into ``_KEYS_BY_CATEGORY`` or list them in "
            "``_NON_PRESET_KEYS``.",
        )
    extra = set(reverse) - set(ALLOWED_CUSTOMIZATION_KEYS)
    if extra:
        raise RuntimeError(
            "Preset categories reference unknown customization keys: "
            f"{sorted(extra)}.",
        )
    return reverse


_KEY_TO_CATEGORY: dict[str, str] = _validate_partition()


def category_for_key(key: str) -> str | None:
    """Return the category id that owns *key*, or ``None`` for unknown keys."""
    return _KEY_TO_CATEGORY.get(key)


def keys_for_category(category: str) -> tuple[str, ...]:
    """Return the customization keys that belong to *category*."""
    return _KEYS_BY_CATEGORY.get(category, ())


def categories_for_keys(keys: Iterable[str]) -> list[str]:
    """Return the category ids covered by *keys*, in canonical order.

    Keys that don't map to any category are ignored (they were already
    filtered out by :func:`filter_to_known` before persistence).
    """
    seen: set[str] = set()
    for key in keys:
        cat = _KEY_TO_CATEGORY.get(key)
        if cat is not None:
            seen.add(cat)
    return [cat for cat in CATEGORY_ORDER if cat in seen]


def filter_to_known(values: dict[str, Any]) -> dict[str, Any]:
    """Return *values* trimmed to keys that map to a known category.

    Unknown keys are silently dropped — the operator's React panel
    only ever sends fields from its own form, so this is a defence
    against a hand-crafted ``POST /presets`` body trying to plant
    arbitrary state into the catalogue.
    """
    if not isinstance(values, dict):
        return {}
    return {k: v for k, v in values.items() if k in _KEY_TO_CATEGORY}
