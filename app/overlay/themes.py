"""Catalogue of preset overlay themes.

A theme is a partial state payload — a dict that ``OverlayStateStore.update_state``
deep-merges into ``data/overlay_state_<hash>.json``. Every theme either flips
``overlay_control.preferredStyle`` (which switches the Jinja template served at
``/overlay/{output_key}``), tweaks ``overlay_control.colors`` (consumed by the
``original``, ``compact``, ``glass``… templates) or both.

Lives in its own module so both the public overlay router (``apply_theme``)
and the admin router (``PATCH /api/v1/admin/custom-overlays/{name}``) can
import it without creating a circular dependency between
``app.overlay.routes`` and ``app.admin.routes``. Fase 2 / M8 will replace
this static dict with a directory-backed catalogue under ``data/themes/``;
keeping the import surface stable now means M8 only has to swap the
implementation.
"""

PRESET_THEMES: dict[str, dict] = {
    "dark": {
        "overlay_control": {
            "colors": {
                "set_bg": "#222222", "set_text": "#FFFFFF",
                "game_bg": "#111111", "game_text": "#FFFFFF",
            }
        }
    },
    "light": {
        "overlay_control": {
            "colors": {
                "set_bg": "#EEEEEE", "set_text": "#222222",
                "game_bg": "#F5F5F5", "game_text": "#111111",
            }
        }
    },
    "esports": {
        "overlay_control": {
            "preferredStyle": "esports",
            "colors": {
                "set_bg": "#0d0d1a", "set_text": "#00FFFF",
                "game_bg": "#0a0a0f", "game_text": "#00FFFF",
            },
        }
    },
    "neo_jersey": {
        "overlay_control": {
            "preferredStyle": "neo_jersey",
        }
    },
    "split_jersey": {
        "overlay_control": {
            "preferredStyle": "split_jersey",
        }
    },
    "clear_jersey": {
        "overlay_control": {
            "preferredStyle": "clear_jersey",
        }
    },
}


def get_theme_names() -> list[str]:
    """Return the list of available theme names in catalogue order."""
    return list(PRESET_THEMES.keys())
