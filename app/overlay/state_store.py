"""Overlay state management — in-memory + JSON file persistence.

Ported from volleyball-scoreboard-overlay/main.py into a reusable class
so the backend can manage overlay state in-process without an external
overlay server.
"""

import asyncio
import copy
import hashlib
import json
import logging
import os
import tempfile
import threading
from typing import Callable, Dict, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


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

    - Clamps ``timeouts_taken`` to [0, 2] (FIVB: max 2 per team per set).
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


def get_default_state(best_of_sets: int = 5) -> dict:
    """Return a blank overlay state."""
    default_logo = os.environ.get(
        "DEFAULT_TEAM_LOGO", "/static/images/default_volleyball.svg"
    )
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


# ---------------------------------------------------------------------------
# OverlayStateStore
# ---------------------------------------------------------------------------


class OverlayStateStore:
    """Manages overlay state with in-memory cache and JSON file persistence.

    Each overlay has a state file at ``data/overlay_state_{id}.json`` and an
    in-memory context dict with its current state and connected client lists.
    """

    def __init__(self, data_dir: str, templates_dir: str):
        self._data_dir = data_dir
        self._templates_dir = templates_dir
        self._overlays: Dict[str, dict] = {}
        self._lock = threading.RLock()
        self._broadcast_callback: Optional[Callable] = None
        self._available_styles: Optional[list] = None
        self._output_key_cache: Dict[str, str] = {}  # output_key -> overlay_id
        os.makedirs(data_dir, exist_ok=True)

    def set_broadcast_callback(self, callback: Callable) -> None:
        """Set the callback invoked after state changes to trigger broadcasts."""
        self._broadcast_callback = callback

    # -- File I/O ----------------------------------------------------------

    @staticmethod
    def _sanitize_id(overlay_id: str) -> str:
        """Strip path separators to prevent path traversal."""
        return os.path.basename(overlay_id)

    def get_state_file_path(self, overlay_id: str) -> str:
        safe_id = self._sanitize_id(overlay_id)
        return os.path.join(self._data_dir, f"overlay_state_{safe_id}.json")

    def _read_state_sync(self, path: str) -> Optional[dict]:
        """Read state from disk synchronously."""
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as exc:
                logger.warning("Failed to load state from '%s': %s", path, exc)
        return None

    @staticmethod
    def _write_state_sync(path: str, state: dict) -> None:
        """Write state to disk atomically via temp file + rename."""
        dir_name = os.path.dirname(path)
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(state, f)
            os.replace(tmp_path, path)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

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
            self._write_state_sync(path, state)
        except Exception as exc:
            logger.warning("Failed to save state for '%s': %s", overlay_id, exc)

    async def save_persisted_state_async(self, overlay_id: str, state: dict) -> None:
        path = self.get_state_file_path(overlay_id)
        try:
            await asyncio.to_thread(self._write_state_sync, path, state)
        except Exception as exc:
            logger.warning("Failed to save state for '%s': %s", overlay_id, exc)

    # -- In-memory context -------------------------------------------------

    def get_overlay_context(self, overlay_id: str) -> dict:
        """Return the in-memory context for *overlay_id*, lazy-loading from disk."""
        with self._lock:
            if overlay_id not in self._overlays:
                self._overlays[overlay_id] = {
                    "state": self.load_persisted_state(overlay_id),
                    "clients": [],
                    "controllers": [],
                }
            ctx = self._overlays[overlay_id]
            if "controllers" not in ctx:
                ctx["controllers"] = []
            return ctx

    def get_state(self, overlay_id: str) -> dict:
        """Return a snapshot of the current state for *overlay_id*."""
        with self._lock:
            return copy.deepcopy(self.get_overlay_context(overlay_id)["state"])

    def overlay_exists(self, overlay_id: str) -> bool:
        """Check whether a state file exists on disk for *overlay_id*."""
        return os.path.exists(self.get_state_file_path(overlay_id))

    # -- Output keys -------------------------------------------------------

    @staticmethod
    def get_output_key(overlay_id: str) -> str:
        """Return a short deterministic hash of the overlay name."""
        return hashlib.sha256(overlay_id.encode()).hexdigest()[:12]

    def resolve_overlay_id(self, id_or_key: str) -> Optional[str]:
        """Resolve an overlay ID or output key to the real overlay ID."""
        if os.path.exists(self.get_state_file_path(id_or_key)):
            return id_or_key
        with self._lock:
            # Check in-memory cache first
            cached = self._output_key_cache.get(id_or_key)
            if cached and os.path.exists(self.get_state_file_path(cached)):
                return cached
            # Scan data dir and rebuild cache
            if os.path.isdir(self._data_dir):
                for filename in os.listdir(self._data_dir):
                    if filename.startswith("overlay_state_") and filename.endswith(".json"):
                        candidate = filename[len("overlay_state_"):-5]
                        key = self.get_output_key(candidate)
                        self._output_key_cache[key] = candidate
                        if key == id_or_key:
                            return candidate
        return None

    # -- Available styles --------------------------------------------------

    def get_available_styles_list(self) -> list:
        """Return available overlay styles (cached after first scan)."""
        with self._lock:
            if self._available_styles is not None:
                return self._available_styles
            excluded = {"mosaic", "base"}
            styles = []
            if os.path.isdir(self._templates_dir):
                for f in os.listdir(self._templates_dir):
                    if f.endswith(".html"):
                        name = f[:-5]
                        label = "default" if name == "index" else name
                        if label not in excluded:
                            styles.append(label)
            self._available_styles = sorted(styles)
            return self._available_styles

    # -- CRUD --------------------------------------------------------------

    def create_overlay(self, overlay_id: str) -> bool:
        """Create a new overlay with default state.  Returns True if created."""
        path = self.get_state_file_path(overlay_id)
        if os.path.exists(path):
            return False
        self.save_persisted_state(overlay_id, get_default_state())
        self._output_key_cache[self.get_output_key(overlay_id)] = overlay_id
        logger.info("Overlay '%s' created", overlay_id)
        return True

    def ensure_overlay(self, overlay_id: str) -> None:
        """Create the overlay if it does not already exist."""
        if not self.overlay_exists(overlay_id):
            self.create_overlay(overlay_id)

    def delete_overlay(self, overlay_id: str) -> bool:
        """Delete an overlay's state file and in-memory context."""
        path = self.get_state_file_path(overlay_id)
        existed = False
        if os.path.exists(path):
            os.remove(path)
            existed = True
        with self._lock:
            if overlay_id in self._overlays:
                del self._overlays[overlay_id]
                existed = True
        self._output_key_cache.pop(self.get_output_key(overlay_id), None)
        if existed:
            logger.info("Overlay '%s' deleted", overlay_id)
        return existed

    def list_overlays(self) -> list:
        """Return a list of ``{id, output_key}`` for all persisted overlays."""
        if not os.path.isdir(self._data_dir):
            return []
        entries = []
        for filename in os.listdir(self._data_dir):
            if filename.startswith("overlay_state_") and filename.endswith(".json"):
                oid = filename[len("overlay_state_"):-5]
                entries.append({"id": oid, "output_key": self.get_output_key(oid)})
        entries.sort(key=lambda e: e["id"])
        return entries

    # -- Raw config (model/customization pass-through) ---------------------

    def get_raw_config(self, overlay_id: str) -> dict:
        """Return ``{model, customization}`` from the overlay state."""
        with self._lock:
            state = self.get_overlay_context(overlay_id)["state"]
            return {
                "model": copy.deepcopy(state.get("raw_remote_model", {})),
                "customization": copy.deepcopy(state.get("raw_remote_customization", {})),
            }

    def set_raw_config(
        self, overlay_id: str,
        model: Optional[dict] = None,
        customization: Optional[dict] = None,
    ) -> None:
        """Persist raw model/customization data into the overlay state."""
        with self._lock:
            ctx = self.get_overlay_context(overlay_id)
            state = ctx["state"]
            if model is not None:
                state["raw_remote_model"] = model
            if customization is not None:
                state["raw_remote_customization"] = customization
                ps = customization.get("preferredStyle")
                if ps is not None:
                    state.setdefault("overlay_control", {})["preferredStyle"] = ps
            snapshot = copy.deepcopy(state)
        self.save_persisted_state(overlay_id, snapshot)
        if self._broadcast_callback:
            self._broadcast_callback(overlay_id)

    # -- State updates -----------------------------------------------------

    async def update_state(self, overlay_id: str, payload: dict) -> None:
        """Deep-merge *payload* into overlay state, normalize, persist, broadcast."""
        with self._lock:
            ctx = self.get_overlay_context(overlay_id)
            deep_merge(ctx["state"], payload)
            normalize_state(ctx["state"])
            snapshot = copy.deepcopy(ctx["state"])
        await self.save_persisted_state_async(overlay_id, snapshot)
        if self._broadcast_callback:
            self._broadcast_callback(overlay_id)

    def update_state_sync(self, overlay_id: str, payload: dict) -> None:
        """Synchronous version of :meth:`update_state`."""
        with self._lock:
            ctx = self.get_overlay_context(overlay_id)
            deep_merge(ctx["state"], payload)
            normalize_state(ctx["state"])
            snapshot = copy.deepcopy(ctx["state"])
        self.save_persisted_state(overlay_id, snapshot)
        if self._broadcast_callback:
            self._broadcast_callback(overlay_id)

    def set_visibility(self, overlay_id: str, show: bool) -> None:
        """Update ``overlay_control.show_main_scoreboard``."""
        with self._lock:
            ctx = self.get_overlay_context(overlay_id)
            ctx["state"].setdefault("overlay_control", {})["show_main_scoreboard"] = show
            snapshot = copy.deepcopy(ctx["state"])
        self.save_persisted_state(overlay_id, snapshot)
        if self._broadcast_callback:
            self._broadcast_callback(overlay_id)
