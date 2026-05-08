"""Scope registry for the preset system.

A "preset" is a named, on-disk subset of an overlay's state that the
operator can save from one OID and replay on another. Each preset
records which *scopes* it covers and a snapshot of the relevant state
keys at save time. This module owns the contract between scope IDs
and the state shape:

* ``SCOPES`` — the public ordered list of scope IDs accepted at the
  admin API surface. Anything outside this set is rejected with 400
  before it reaches disk.
* ``extract(state, scope_id)`` — pull the sub-state a scope cares
  about out of an :class:`OverlayStateStore` snapshot.
* ``apply_payload(snapshot, scope_id)`` — take a snapshot previously
  produced by :func:`extract` and turn it into the partial dict that
  ``OverlayStateStore.update_state`` deep-merges into the target.

Keeping the two halves in this single module means a scope is added /
renamed in exactly one place: register it in ``_SCOPE_HANDLERS`` and
the create / apply / list endpoints inherit the change automatically.

The intentional design omissions:

* Match-state keys (``points``, ``sets_won``, ``set_history``,
  ``serving``, ``timeouts_taken``, ``current_set``, ``match_started_at``)
  are **never** copied — they describe the live game, not a reusable
  configuration. Letting an operator restore them by accident would
  silently rewind a real match.
* ``raw_remote_model`` / ``raw_remote_customization`` are also
  excluded; they are the overlays.uno passthrough payloads handled by
  ``set_raw_config`` and live outside the preset model. Roundtripping
  them is the job of the future overlay export/import (M10), not of
  preset apply.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

# ---------------------------------------------------------------------------
# Scope handlers
# ---------------------------------------------------------------------------


def _extract_team(state: dict, slot: str) -> dict:
    team = state.get(slot) or {}
    # Only keep the identity-level keys; in particular skip points,
    # sets_won, set_history, serving and timeouts_taken so a preset
    # apply never overwrites a live match score.
    return {
        key: team.get(key)
        for key in ("name", "short_name", "color_primary",
                    "color_secondary", "logo_url")
        if team.get(key) is not None
    }


def _apply_team(snapshot: dict, slot: str) -> dict:
    if not snapshot:
        return {}
    return {slot: dict(snapshot)}


def _extract_overlay_layout(state: dict) -> dict:
    geometry = (state.get("overlay_control") or {}).get("geometry")
    return {"geometry": dict(geometry)} if isinstance(geometry, dict) and geometry else {}


def _apply_overlay_layout(snapshot: dict) -> dict:
    geometry = snapshot.get("geometry")
    if not isinstance(geometry, dict) or not geometry:
        return {}
    return {"overlay_control": {"geometry": dict(geometry)}}


def _extract_overlay_colors(state: dict) -> dict:
    colors = (state.get("overlay_control") or {}).get("colors")
    return {"colors": dict(colors)} if isinstance(colors, dict) and colors else {}


def _apply_overlay_colors(snapshot: dict) -> dict:
    colors = snapshot.get("colors")
    if not isinstance(colors, dict) or not colors:
        return {}
    return {"overlay_control": {"colors": dict(colors)}}


def _extract_overlay_style(state: dict) -> dict:
    ps = (state.get("overlay_control") or {}).get("preferredStyle")
    return {"preferredStyle": ps} if isinstance(ps, str) and ps else {}


def _apply_overlay_style(snapshot: dict) -> dict:
    ps = snapshot.get("preferredStyle")
    if not isinstance(ps, str) or not ps:
        return {}
    return {"overlay_control": {"preferredStyle": ps}}


# Each entry maps scope_id → (extractor, applier, human_label).
# ``human_label`` is what the manager UI renders next to the checkbox
# so the source of truth for the label lives next to the implementation.
_SCOPE_HANDLERS: dict[
    str,
    tuple[Callable[[dict], dict], Callable[[dict], dict], str],
] = {
    "team_home": (
        lambda s: _extract_team(s, "team_home"),
        lambda snap: _apply_team(snap, "team_home"),
        "Home team identity (name, short name, colors, logo)",
    ),
    "team_away": (
        lambda s: _extract_team(s, "team_away"),
        lambda snap: _apply_team(snap, "team_away"),
        "Away team identity (name, short name, colors, logo)",
    ),
    "overlay_layout": (
        _extract_overlay_layout,
        _apply_overlay_layout,
        "Overlay position and size (geometry)",
    ),
    "overlay_colors": (
        _extract_overlay_colors,
        _apply_overlay_colors,
        "Overlay colors (set/game backgrounds and text)",
    ),
    "overlay_style": (
        _extract_overlay_style,
        _apply_overlay_style,
        "Overlay style (preferredStyle template)",
    ),
}


# Public ordered list — the order is what the UI renders and what
# sets the canonical column order in any future export format.
SCOPES: tuple[str, ...] = tuple(_SCOPE_HANDLERS.keys())


def is_known_scope(scope_id: str) -> bool:
    return scope_id in _SCOPE_HANDLERS


def scope_label(scope_id: str) -> str:
    """Return the human-readable label for *scope_id*, or the id itself."""
    handler = _SCOPE_HANDLERS.get(scope_id)
    return handler[2] if handler else scope_id


def list_scopes_with_labels() -> list[dict[str, str]]:
    """Return ``[{id, label}, ...]`` for the manager UI to render."""
    return [
        {"id": scope_id, "label": handler[2]}
        for scope_id, handler in _SCOPE_HANDLERS.items()
    ]


def extract(state: dict, scope_id: str) -> dict:
    """Return the snapshot for *scope_id* drawn from *state*.

    Empty dict signals "this OID has nothing to save under that
    scope" — callers should drop the scope from the preset rather
    than persisting an empty payload that would replay as a no-op.
    """
    handler = _SCOPE_HANDLERS.get(scope_id)
    if handler is None:
        return {}
    return handler[0](state) or {}


def apply_payload(snapshot: dict, scope_id: str) -> dict[str, Any]:
    """Return the partial state ``update_state`` should deep-merge.

    Empty dict means "the snapshot does not carry enough to actually
    apply this scope" — the caller should skip it rather than firing
    a redundant write.
    """
    handler = _SCOPE_HANDLERS.get(scope_id)
    if handler is None:
        return {}
    return handler[1](snapshot or {}) or {}


def merge_payloads(payloads: list[dict]) -> dict:
    """Deep-merge a sequence of ``update_state`` payloads in order.

    Later payloads win on conflicts. Used to fold the per-scope
    payloads from :func:`apply_payload` into a single
    ``update_state`` call so an apply triggers exactly one disk
    write and one WebSocket broadcast — same coalescing rationale
    as the ``patch_custom_overlay`` review fix.
    """
    merged: dict = {}
    for payload in payloads:
        _deep_merge(merged, payload)
    return merged


def _deep_merge(base: dict, overlay: dict) -> dict:
    for key, value in overlay.items():
        if (
            key in base
            and isinstance(base[key], dict)
            and isinstance(value, dict)
        ):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base
