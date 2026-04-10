"""Overlay state persistence and in-memory cache.

Manages overlay state as JSON files on disk with an in-memory cache.
Ported from the standalone overlay server (volleyball-scoreboard-overlay).
"""

import asyncio
import hashlib
import json
import logging
import os
from typing import Callable, Dict, Optional

logger = logging.getLogger("OverlayStateStore")


def deep_merge(base: dict, update: dict) -> dict:
    """Recursively merge *update* into *base* in place and return *base*."""
    for key, value in update.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def normalize_state(state: dict) -> None:
    """Enforce business rules on the merged state in place.

    - Clamps ``timeouts_taken`` to [0, 2] (FIVB: max 2 timeouts per team per set).
    - Trims ``set_history`` to keys valid for ``best_of_sets``.
    """
    best_of_sets = state.get("match_info", {}).get("best_of_sets", 5)
    valid_set_keys = {f"set_{i}" for i in range(1, best_of_sets + 1)}

    for team_key in ("team_home", "team_away"):
        team = state.get(team_key)
        if not isinstance(team, dict):
            continue
        if "timeouts_taken" in team:
            try:
                team["timeouts_taken"] = max(0, min(2, int(team["timeouts_taken"])))
            except (TypeError, ValueError):
                team["timeouts_taken"] = 0
        if "set_history" in team and isinstance(team["set_history"], dict):
            team["set_history"] = {
                k: v for k, v in team["set_history"].items() if k in valid_set_keys
            }


class OverlayStateStore:
    """Manages overlay state persistence and in-memory cache."""

    def __init__(self, data_dir: str, templates_dir: str):
        self._data_dir = data_dir
        self._templates_dir = templates_dir
        os.makedirs(data_dir, exist_ok=True)
        # In-memory state: {overlay_id: {"state": dict}}
        self._overlays: Dict[str, dict] = {}
        # Callback for triggering broadcasts after state changes
        self._on_state_changed: Optional[Callable] = None

    def set_broadcast_callback(self, callback: Callable) -> None:
        """Set the callback invoked after state changes (typically schedules a broadcast)."""
        self._on_state_changed = callback

    # -- File paths -----------------------------------------------------------

    def get_state_file_path(self, overlay_id: str) -> str:
        return os.path.join(self._data_dir, f"overlay_state_{overlay_id}.json")

    # -- Persistence ----------------------------------------------------------

    def _read_state_sync(self, path: str):
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as exc:
                logger.warning("Failed to load state from '%s': %s", path, exc)
        return None

    def load_persisted_state(self, overlay_id: str) -> dict:
        path = self.get_state_file_path(overlay_id)
        state = self._read_state_sync(path)
        return state if state is not None else get_default_state()

    async def load_persisted_state_async(self, overlay_id: str) -> dict:
        path = self.get_state_file_path(overlay_id)
        state = await asyncio.to_thread(self._read_state_sync, path)
        return state if state is not None else get_default_state()

    def save_persisted_state(self, overlay_id: str, state: dict) -> None:
        path = self.get_state_file_path(overlay_id)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(state, f)
        except Exception as exc:
            logger.warning("Failed to save state for '%s': %s", overlay_id, exc)

    async def save_persisted_state_async(self, overlay_id: str, state: dict) -> None:
        path = self.get_state_file_path(overlay_id)
        try:
            await asyncio.to_thread(self._write_state_sync, path, state)
        except Exception as exc:
            logger.warning("Failed to save state for '%s': %s", overlay_id, exc)

    @staticmethod
    def _write_state_sync(path: str, state: dict):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f)

    # -- In-memory context ----------------------------------------------------

    def get_overlay_context(self, overlay_id: str) -> dict:
        """Get or create in-memory context for an overlay."""
        if overlay_id not in self._overlays:
            self._overlays[overlay_id] = {
                "state": self.load_persisted_state(overlay_id),
            }
        return self._overlays[overlay_id]

    def get_state(self, overlay_id: str) -> dict:
        """Return the current state dict for an overlay."""
        return self.get_overlay_context(overlay_id)["state"]

    def overlay_exists(self, overlay_id: str) -> bool:
        return os.path.exists(self.get_state_file_path(overlay_id))

    # -- Output keys ----------------------------------------------------------

    @staticmethod
    def get_output_key(overlay_id: str) -> str:
        """Deterministic SHA256 hash for unpredictable public URLs."""
        return hashlib.sha256(overlay_id.encode()).hexdigest()[:12]

    def resolve_overlay_id(self, id_or_key: str) -> Optional[str]:
        """Resolve an overlay ID or output key to the real overlay ID."""
        if os.path.exists(self.get_state_file_path(id_or_key)):
            return id_or_key
        if os.path.isdir(self._data_dir):
            for filename in os.listdir(self._data_dir):
                if filename.startswith("overlay_state_") and filename.endswith(".json"):
                    candidate = filename[len("overlay_state_"):-5]
                    if self.get_output_key(candidate) == id_or_key:
                        return candidate
        return None

    # -- Available styles -----------------------------------------------------

    def get_available_styles_list(self) -> list:
        excluded = {"mosaic", "base"}
        available = []
        if os.path.isdir(self._templates_dir):
            for f in os.listdir(self._templates_dir):
                if f.endswith(".html"):
                    name = f[:-5]
                    label = "default" if name == "index" else name
                    if label not in excluded:
                        available.append(label)
        return sorted(available)

    # -- CRUD -----------------------------------------------------------------

    def create_overlay(self, overlay_id: str) -> bool:
        """Create an overlay. Returns True if created, False if already exists."""
        path = self.get_state_file_path(overlay_id)
        if os.path.exists(path):
            return False
        self.save_persisted_state(overlay_id, get_default_state())
        logger.info("Overlay '%s' created", overlay_id)
        return True

    def ensure_overlay(self, overlay_id: str) -> None:
        """Create the overlay if it doesn't exist."""
        if not self.overlay_exists(overlay_id):
            self.create_overlay(overlay_id)

    async def delete_overlay(self, overlay_id: str) -> bool:
        """Delete an overlay. Returns True if it existed."""
        path = self.get_state_file_path(overlay_id)
        existed = False
        if os.path.exists(path):
            os.remove(path)
            existed = True
        if overlay_id in self._overlays:
            del self._overlays[overlay_id]
            existed = True
        if existed:
            logger.info("Overlay '%s' deleted", overlay_id)
        return existed

    def list_overlays(self) -> list:
        """List all persisted overlays."""
        if not os.path.exists(self._data_dir):
            return []
        entries = []
        for filename in os.listdir(self._data_dir):
            if filename.startswith("overlay_state_") and filename.endswith(".json"):
                oid = filename[len("overlay_state_"):-5]
                entries.append({
                    "id": oid,
                    "output_key": self.get_output_key(oid),
                })
        entries.sort(key=lambda e: e["id"])
        return entries

    # -- Raw config -----------------------------------------------------------

    def get_raw_config(self, overlay_id: str) -> dict:
        """Return raw model + customization from overlay state."""
        state = self.get_state(overlay_id)
        return {
            "model": state.get("raw_remote_model", {}),
            "customization": state.get("raw_remote_customization", {}),
        }

    def set_raw_config(self, overlay_id: str, model=None, customization=None) -> None:
        """Update raw model and/or customization in overlay state."""
        ctx = self.get_overlay_context(overlay_id)
        state = ctx["state"]
        if model is not None:
            state["raw_remote_model"] = model
        if customization is not None:
            state["raw_remote_customization"] = customization
            ps = customization.get("preferredStyle") if isinstance(customization, dict) else None
            if ps is not None:
                state.setdefault("overlay_control", {})["preferredStyle"] = ps
        self.save_persisted_state(overlay_id, state)

    # -- State updates --------------------------------------------------------

    async def update_state(self, overlay_id: str, payload: dict) -> None:
        """Deep-merge payload into overlay state, normalize, persist, and broadcast."""
        ctx = self.get_overlay_context(overlay_id)
        deep_merge(ctx["state"], payload)
        normalize_state(ctx["state"])
        await self.save_persisted_state_async(overlay_id, ctx["state"])
        if self._on_state_changed:
            self._on_state_changed(overlay_id)

    def update_state_sync(self, overlay_id: str, payload: dict) -> None:
        """Synchronous version of update_state for use from sync code paths."""
        ctx = self.get_overlay_context(overlay_id)
        deep_merge(ctx["state"], payload)
        normalize_state(ctx["state"])
        self.save_persisted_state(overlay_id, ctx["state"])
        if self._on_state_changed:
            self._on_state_changed(overlay_id)

    def set_visibility(self, overlay_id: str, show: bool) -> None:
        """Set overlay visibility and trigger broadcast."""
        ctx = self.get_overlay_context(overlay_id)
        ctx["state"].setdefault("overlay_control", {})["show_main_scoreboard"] = show
        self.save_persisted_state(overlay_id, ctx["state"])
        if self._on_state_changed:
            self._on_state_changed(overlay_id)


# -- Module-level helpers -----------------------------------------------------


def get_default_state(best_of_sets: int = 5) -> dict:
    """Return a blank overlay state."""
    default_logo = os.environ.get("DEFAULT_TEAM_LOGO", "/static/images/default_volleyball.svg")
    set_history = {f"set_{i}": 0 for i in range(1, best_of_sets + 1)}
    return {
        "match_info": {
            "tournament": "Superliga Masculina",
            "phase": "Playoffs - Final",
            "best_of_sets": best_of_sets,
            "current_set": 1,
        },
        "team_home": {
            "name": "HOME TEAM",
            "short_name": "HOM",
            "color_primary": "#E21836",
            "color_secondary": "#FFFFFF",
            "logo_url": default_logo,
            "sets_won": 0,
            "points": 0,
            "serving": False,
            "timeouts_taken": 0,
            "set_history": dict(set_history),
        },
        "team_away": {
            "name": "AWAY TEAM",
            "short_name": "AWA",
            "color_primary": "#0047AB",
            "color_secondary": "#FFD700",
            "logo_url": default_logo,
            "sets_won": 0,
            "points": 0,
            "serving": False,
            "timeouts_taken": 0,
            "set_history": dict(set_history),
        },
        "overlay_control": {
            "show_main_scoreboard": True,
            "show_bottom_ticker": False,
            "ticker_message": "",
            "show_player_stats": False,
            "player_stats_data": None,
        },
    }
