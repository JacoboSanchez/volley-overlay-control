"""Translate admin-side preset snapshots to operator-side flat customization.

Admin presets (see :mod:`app.api.preset_scopes`) capture nested-shape state
keys (``team_home.color_primary``, ``overlay_control.geometry.h``, …)
extracted from the structured layer of an OID's overlay state. The
operator's React control panel, however, edits a flat dict of
``ALLOWED_CUSTOMIZATION_KEYS`` (``Team 1 Color``, ``Height``, …) that
ultimately persists under ``raw_remote_customization`` in the same
overlay state file. Aplicar un preset desde el ConfigPanel requiere
traducir el snapshot anidado al subset de claves planas que la capa
operador entiende.

The mapping is best-effort: a few nested keys (e.g. ``team_home.short_name``)
have no flat equivalent in the operator's allow-list and are silently
dropped. The ``Team N Text Color`` slot maps to ``color_secondary`` from
the snapshot — semantically the closest pair (the text-on-primary slot
the scoreboards use), even though ``color_secondary`` is a more general
field upstream.

Theme apply (``id="theme:<key>"``) bypasses this module entirely — env-var
``APP_THEMES`` are already shaped as flat dicts.
"""

from __future__ import annotations

from typing import Any

# Each scope maps to a list of ``(snapshot_path, flat_key)`` pairs.
# ``snapshot_path`` is a dotted lookup inside the per-scope snapshot dict
# returned by :func:`app.api.preset_scopes.extract`. Missing values along
# the path skip that mapping rather than writing ``None`` (which would
# clobber existing operator state).
_SCOPE_TRANSLATION: dict[str, list[tuple[str, str]]] = {
    "team_home": [
        ("name", "Team 1 Name"),
        ("color_primary", "Team 1 Color"),
        ("color_secondary", "Team 1 Text Color"),
        ("logo_url", "Team 1 Logo"),
    ],
    "team_away": [
        ("name", "Team 2 Name"),
        ("color_primary", "Team 2 Color"),
        ("color_secondary", "Team 2 Text Color"),
        ("logo_url", "Team 2 Logo"),
    ],
    "overlay_layout": [
        ("geometry.x", "Left-Right"),
        ("geometry.y", "Up-Down"),
        ("geometry.w", "Width"),
        ("geometry.h", "Height"),
    ],
    "overlay_colors": [
        ("colors.set_bg", "Color 1"),
        ("colors.set_text", "Text Color 1"),
        ("colors.game_bg", "Color 2"),
        ("colors.game_text", "Text Color 2"),
    ],
    "overlay_style": [
        ("preferredStyle", "preferredStyle"),
    ],
}


def _lookup(snapshot: dict, dotted: str) -> Any | None:
    cursor: Any = snapshot
    for part in dotted.split("."):
        if not isinstance(cursor, dict):
            return None
        cursor = cursor.get(part)
        if cursor is None:
            return None
    return cursor


def translate_snapshot(snapshot: dict, scope: str) -> dict[str, Any]:
    """Return the flat-key patch for *scope*'s *snapshot*.

    Empty dict means the snapshot carried no translatable keys for this
    scope — the caller should skip the scope rather than firing a no-op
    write.
    """
    rules = _SCOPE_TRANSLATION.get(scope)
    if not rules or not isinstance(snapshot, dict):
        return {}
    out: dict[str, Any] = {}
    for source_path, flat_key in rules:
        value = _lookup(snapshot, source_path)
        if value is None:
            continue
        out[flat_key] = value
    return out


def translate_record(
    record: dict, scopes: list[str] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Translate a preset record's snapshots to a single flat-key patch.

    *scopes* limits which of the record's scopes contribute. ``None``
    means "all scopes the record carries". Returns ``(patch, applied)``
    where ``applied`` lists the scopes that contributed at least one
    flat key — useful for the API response and operator-facing
    "applied" pill.
    """
    snapshots = record.get("snapshots") or {}
    available = list(record.get("scopes") or [])
    if scopes is None:
        wanted = available
    else:
        wanted = [s for s in scopes if s in available]
    merged: dict[str, Any] = {}
    applied: list[str] = []
    for scope in wanted:
        snapshot = snapshots.get(scope)
        if not isinstance(snapshot, dict) or not snapshot:
            continue
        patch = translate_snapshot(snapshot, scope)
        if patch:
            merged.update(patch)
            applied.append(scope)
    return merged, applied
