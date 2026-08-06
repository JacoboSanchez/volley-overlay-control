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
import re
import threading
from collections.abc import Callable, Iterator

from app.api._persistence_paths import DEFAULT_HASH_LEN, atomic_write_json, hashed_filename
from app.env_vars_manager import EnvVarsManager
from app.id_validation import is_valid_overlay_id, validate_overlay_id
from app.overlay.style_catalog import StyleCatalog
from app.overlay_key import is_valid_skey

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


# Paths in the broadcast payload whose nested-dict values must FULLY
# REPLACE the corresponding subtree in the merged state instead of
# being deep-merged into it. These fields are derived from the per-OID
# audit log on every broadcast — a deep-merge would leave stale per-set
# entries behind after ``GameService.reset`` clears the audit, so a
# fresh empty payload would never overwrite e.g. ``points_by_set``
# entries from the previous match. The spectator page would then keep
# rendering the stale chart / time history even after the operator
# reset the scoreboard.
#
# The per-set buckets (``*_by_set``) are the ones that genuinely lose
# keys between broadcasts: a set with no recorded events drops out of
# the map entirely. ``point_types_by_set`` is the subtlest case — its
# set keys only exist while points carry scouting tags, so a match
# scored without per-point stats sends ``{}`` and a plain deep-merge
# would keep the *previous* match's tagged-point breakdown visible in
# the set-summary recap (and every other overlay) indefinitely.
_REPLACE_SUBTREES: tuple[tuple[str, ...], ...] = (
    ("overlay_control", "points_by_set"),
    ("overlay_control", "timeouts_by_set"),
    ("overlay_control", "stats", "set_durations"),
    ("overlay_control", "stats", "services"),
    ("overlay_control", "stats", "services_by_set"),
    ("overlay_control", "stats", "longest_streak_by_set"),
    ("overlay_control", "stats", "point_types_by_set"),
    ("overlay_control", "stats", "points_history"),
)


def _replace_subtrees(state: dict, payload: dict) -> None:
    """Force-replace specific subtrees on *state* with values from *payload*.

    Run after :func:`deep_merge` so any audit-derived dict whose keys
    can disappear between broadcasts (e.g. per-set buckets after a
    reset) gets the fresh value, not a stale-key union.
    """
    for path in _REPLACE_SUBTREES:
        node_p: object = payload
        for key in path:
            if not isinstance(node_p, dict) or key not in node_p:
                node_p = None
                break
            node_p = node_p[key]
        if node_p is None:
            continue
        node_s: object = state
        for key in path[:-1]:
            if not isinstance(node_s, dict):
                node_s = None
                break
            node_s = node_s.setdefault(key, {})
        if isinstance(node_s, dict):
            node_s[path[-1]] = node_p


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
    default_logo = EnvVarsManager.get_str_env(
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


# Length of the hex SHA-256 prefix used to derive on-disk filenames from
# user-supplied overlay ids. 20 hex chars = 80 bits, well above the birthday
# bound for any realistic overlay count.
_FILENAME_HASH_LEN = DEFAULT_HASH_LEN

# Matches the hashed basename produced by ``_hashed_basename``. Used during
# legacy-file migration to skip files that are already in the new format.
_HASHED_FILENAME_PATTERN = re.compile(
    r"^overlay_state_[0-9a-f]{" + str(_FILENAME_HASH_LEN) + r"}\.json$"
)

class OverlayStateStore:
    """Manages overlay state with in-memory cache and JSON file persistence.

    Each overlay has a state file at
    ``data/overlay_state_{sha256(id)[:20]}.json`` — the hex-only basename
    breaks the taint flow from user input to filesystem paths that CodeQL
    tracks. The original overlay id is stored inside the JSON payload under
    ``_meta.overlay_id`` so listings and cache lookups can recover it.
    """

    def __init__(self, data_dir: str, templates_dir: str) -> None:
        self._data_dir = data_dir
        self._overlays: dict[str, dict] = {}
        self._lock = threading.RLock()
        self._style_catalog = StyleCatalog(templates_dir, lock=self._lock)
        # Serializes each overlay's mutation -> snapshot -> disk-write sequence
        # without making unrelated overlays wait on one another. These locks
        # are always acquired before ``self._lock``.
        self._persistence_locks: dict[str, threading.Lock] = {}
        self._broadcast_callback: Callable[[str], None] | None = None
        # Maps any accepted URL token (output_key or raw overlay_id) to the
        # real overlay id. Populated lazily by resolve_overlay_id and kept
        # in sync by create/copy/delete.
        self._output_key_cache: dict[str, str] = {}
        self._all_overlays_scanned = False
        os.makedirs(data_dir, exist_ok=True)

    def set_broadcast_callback(
        self,
        callback: Callable[[str], None],
    ) -> None:
        """Set the callback invoked after state changes to trigger broadcasts."""
        self._broadcast_callback = callback

    # -- File I/O ----------------------------------------------------------

    @staticmethod
    def _sanitize_id(overlay_id: str) -> str:
        """Validate *overlay_id* as a filesystem-safe identifier.

        Accepts either a bare overlay id (legacy/single-tenant) or a
        per-user storage key ``<user_id>:<oid>`` (:func:`app.overlay_key`).
        Both shapes are path-safe — no ``/`` and no ``..`` — so this stays
        the single choke point between caller input and the on-disk
        ``overlay_state_<hash>.json`` paths. Raises ``ValueError`` otherwise.
        """
        if is_valid_skey(overlay_id):
            return overlay_id
        return validate_overlay_id(overlay_id)

    @staticmethod
    def _hashed_basename(overlay_id: str) -> str:
        """Return the on-disk basename for *overlay_id*.

        The hex-only digest means the final path is built from
        ``self._data_dir`` (trusted) plus a fixed-alphabet suffix, so
        CodeQL's ``py/path-injection`` taint tracker sees the user input
        replaced with a hash output at this boundary.
        """
        return hashed_filename("overlay_state_", overlay_id)

    def get_state_file_path(self, overlay_id: str) -> str:
        safe_id = self._sanitize_id(overlay_id)
        return os.path.join(self._data_dir, self._hashed_basename(safe_id))

    def _read_state_sync(self, path: str) -> dict | None:
        """Read state from disk synchronously."""
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError) as exc:
                # Narrow on purpose: a bad file or unreadable disk is
                # something we recover from by falling back to defaults,
                # but a programming error (KeyError, AttributeError…)
                # should surface, not be silently downgraded.
                logger.warning("Failed to load state from '%s': %s", path, exc)
        return None

    @staticmethod
    def _write_state_sync(path: str, state: dict) -> None:
        """Write state to disk atomically via temp file + rename."""
        atomic_write_json(path, state)

    @staticmethod
    def _stamp_meta(state: dict, overlay_id: str) -> dict:
        """Inject ``_meta.overlay_id`` so the id can be recovered from the file.

        Needed because filenames no longer carry the id (they're hashes).
        Returns *state* for call-site convenience.
        """
        meta = state.setdefault("_meta", {})
        meta["overlay_id"] = overlay_id
        return state

    def load_persisted_state(self, overlay_id: str) -> dict:
        path = self.get_state_file_path(overlay_id)
        state = self._read_state_sync(path)
        return state if state is not None else get_default_state()

    async def load_persisted_state_async(self, overlay_id: str) -> dict:
        return await asyncio.to_thread(self.load_persisted_state, overlay_id)

    def _save_persisted_state_unlocked(self, overlay_id: str, state: dict) -> None:
        """Persist *state* while the caller holds the overlay's write lock."""
        path = self.get_state_file_path(overlay_id)
        self._stamp_meta(state, overlay_id)
        try:
            self._write_state_sync(path, state)
        except OSError as exc:
            # _write_state_sync uses tempfile + os.replace; failure modes
            # are filesystem-level (no space, permissions, missing dir).
            logger.warning("Failed to save state for '%s': %s", overlay_id, exc)

    def save_persisted_state(self, overlay_id: str, state: dict) -> None:
        with self._get_persistence_lock(overlay_id):
            self._save_persisted_state_unlocked(overlay_id, state)

    async def save_persisted_state_async(self, overlay_id: str, state: dict) -> None:
        await asyncio.to_thread(self.save_persisted_state, overlay_id, state)

    def _get_persistence_lock(self, overlay_id: str) -> threading.Lock:
        """Return the stable per-overlay lock used to order disk snapshots."""
        with self._lock:
            return self._persistence_locks.setdefault(overlay_id, threading.Lock())

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
        """Check whether a state file exists on disk for *overlay_id*.

        Returns False for ids that fail the sanitizer so the public contract
        (a bool) is preserved — callers probing with arbitrary user input
        get the same "no such overlay" answer they'd get for a well-formed
        id that happens to not exist.
        """
        try:
            path = self.get_state_file_path(overlay_id)
        except ValueError:
            return False
        return os.path.exists(path)

    # -- Output keys -------------------------------------------------------

    @staticmethod
    def get_output_key(overlay_id: str) -> str:
        """Return a short deterministic hash of the overlay name."""
        return hashlib.sha256(overlay_id.encode()).hexdigest()[:12]

    def resolve_overlay_id(self, token: str) -> str | None:
        """Resolve a URL path segment to its real overlay ID.

        Accepts either the SHA-256 output key or the raw overlay id.
        Returning on the raw id keeps the friendly ``/overlay/{id}``
        and ``/ws/{id}`` URLs working alongside the capability-style
        ``/overlay/{output_key}`` form.

        Both forms are cached, and a "fully scanned" flag short-circuits
        lookups for unknown tokens so invalid requests do not keep
        hammering ``os.listdir``.
        """
        with self._lock:
            cached = self._output_key_cache.get(token)
            if cached is not None:
                return cached
            if self._all_overlays_scanned:
                return None
            self._populate_cache_locked()
            return self._output_key_cache.get(token)

    def _iter_persisted_ids(self) -> Iterator[tuple[str, str]]:
        """Yield ``(overlay_id, basename)`` for every state file on disk.

        Filenames are hash-based so the id is recovered from
        ``_meta.overlay_id`` inside each payload. Files whose contents do
        not parse or lack ``_meta.overlay_id`` are skipped with a warning
        (they never round-trip through :meth:`save_persisted_state` and
        should not exist in a healthy deployment).
        """
        if not os.path.isdir(self._data_dir):
            return
        for filename in os.listdir(self._data_dir):
            if not _HASHED_FILENAME_PATTERN.fullmatch(filename):
                continue
            path = os.path.join(self._data_dir, filename)
            try:
                with open(path, encoding="utf-8") as f:
                    payload = json.load(f)
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning("Skipping unreadable state file '%s': %s", filename, exc)
                continue
            oid = (payload or {}).get("_meta", {}).get("overlay_id")
            if not (is_valid_overlay_id(oid) or is_valid_skey(oid)):
                logger.warning("State file '%s' missing valid _meta.overlay_id", filename)
                continue
            yield oid, filename

    def _populate_cache_locked(self) -> None:
        """Walk the data directory once and index every overlay by both
        its raw id and its output key. Caller must hold ``self._lock``.
        """
        if self._all_overlays_scanned:
            return
        for oid, _ in self._iter_persisted_ids():
            self._output_key_cache[oid] = oid
            self._output_key_cache[self.get_output_key(oid)] = oid
        self._all_overlays_scanned = True

    # -- Available styles --------------------------------------------------

    def get_available_styles_list(self) -> list[str]:
        return self._style_catalog.get_available_styles_list()

    def get_renderable_styles(self) -> list[str]:
        return self._style_catalog.get_renderable_styles()

    # -- Style capabilities ------------------------------------------------

    def get_style_capabilities(self) -> dict[str, dict[str, bool]]:
        return self._style_catalog.get_style_capabilities()

    # Compatibility properties for fixtures and extensions that clear the
    # historical store-level caches between test/application lifecycles.
    @property
    def _available_styles(self) -> list[str] | None:
        return self._style_catalog._available_styles

    @_available_styles.setter
    def _available_styles(self, value: list[str] | None) -> None:
        self._style_catalog._available_styles = value

    @property
    def _renderable_styles(self) -> list[str] | None:
        return self._style_catalog._renderable_styles

    @_renderable_styles.setter
    def _renderable_styles(self, value: list[str] | None) -> None:
        self._style_catalog._renderable_styles = value

    @property
    def _style_capabilities(self) -> dict[str, dict[str, bool]] | None:
        return self._style_catalog._style_capabilities

    @_style_capabilities.setter
    def _style_capabilities(
        self,
        value: dict[str, dict[str, bool]] | None,
    ) -> None:
        self._style_catalog._style_capabilities = value

    # -- CRUD --------------------------------------------------------------

    def create_overlay(self, overlay_id: str) -> bool:
        """Create a new overlay with default state.  Returns True if created."""
        try:
            path = self.get_state_file_path(overlay_id)
        except ValueError:
            logger.warning("create_overlay rejected invalid id: %r", overlay_id)
            return False
        with self._get_persistence_lock(overlay_id), self._lock:
            # Hold both locks across the existence check and write so two
            # concurrent first-touches cannot both create default state.
            if os.path.exists(path):
                return False
            self._save_persisted_state_unlocked(
                overlay_id, get_default_state()
            )
            self._output_key_cache[overlay_id] = overlay_id
            self._output_key_cache[self.get_output_key(overlay_id)] = overlay_id
        logger.info("Overlay '%s' created", overlay_id)
        return True

    def ensure_overlay(self, overlay_id: str) -> None:
        """Create the overlay if it does not already exist."""
        if not self.overlay_exists(overlay_id):
            self.create_overlay(overlay_id)

    def delete_overlay(self, overlay_id: str) -> bool:
        """Delete an overlay's state file and in-memory context."""
        try:
            path = self.get_state_file_path(overlay_id)
        except ValueError:
            logger.warning("delete_overlay rejected invalid id: %r", overlay_id)
            return False
        existed = False
        with self._get_persistence_lock(overlay_id):
            if os.path.exists(path):
                os.remove(path)
                existed = True
            with self._lock:
                if overlay_id in self._overlays:
                    del self._overlays[overlay_id]
                    existed = True
                self._output_key_cache.pop(overlay_id, None)
                self._output_key_cache.pop(self.get_output_key(overlay_id), None)
        if existed:
            logger.info("Overlay '%s' deleted", overlay_id)
        return existed

    def list_overlays(self) -> list:
        """Return a list of ``{id, output_key}`` for all persisted overlays."""
        entries = [
            {"id": oid, "output_key": self.get_output_key(oid)}
            for oid, _ in self._iter_persisted_ids()
        ]
        entries.sort(key=lambda e: e["id"])
        return entries

    def copy_overlay(self, source_id: str, target_id: str) -> bool:
        """Clone *source_id*'s persisted state into *target_id*.

        Returns True on success, False when the source does not exist or
        the target already exists. Useful for creating a new overlay that
        inherits the source's configuration (colors, preferredStyle,
        customization, match data).
        """
        if not self.overlay_exists(source_id):
            return False
        source_state = self.load_persisted_state(source_id)
        with self._get_persistence_lock(target_id):
            if self.overlay_exists(target_id):
                return False
            self._save_persisted_state_unlocked(
                target_id, copy.deepcopy(source_state)
            )
            with self._lock:
                self._output_key_cache[target_id] = target_id
                self._output_key_cache[self.get_output_key(target_id)] = target_id
        logger.info("Overlay '%s' copied from '%s'", target_id, source_id)
        return True

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
        model: dict | None = None,
        customization: dict | None = None,
    ) -> None:
        """Persist raw model/customization data into the overlay state."""
        def apply(state: dict) -> None:
            if model is not None:
                state["raw_remote_model"] = model
            if customization is not None:
                state["raw_remote_customization"] = customization
                ps = customization.get("preferredStyle")
                if ps is not None:
                    state.setdefault("overlay_control", {})["preferredStyle"] = ps

        self._mutate_and_persist(overlay_id, apply)
        if self._broadcast_callback:
            self._broadcast_callback(overlay_id)

    # -- State updates -----------------------------------------------------

    def _mutate_and_persist(
        self, overlay_id: str, mutation: Callable[[dict], None],
    ) -> None:
        """Apply *mutation* and persist its snapshot in per-overlay order."""
        with self._get_persistence_lock(overlay_id):
            with self._lock:
                state = self.get_overlay_context(overlay_id)["state"]
                mutation(state)
                snapshot = copy.deepcopy(state)
            self._save_persisted_state_unlocked(overlay_id, snapshot)

    def _update_state_and_persist(self, overlay_id: str, payload: dict) -> None:
        """Shared implementation for synchronous and asynchronous updates."""
        def apply(state: dict) -> None:
            deep_merge(state, payload)
            _replace_subtrees(state, payload)
            normalize_state(state)

        self._mutate_and_persist(overlay_id, apply)

    async def update_state(self, overlay_id: str, payload: dict) -> None:
        """Deep-merge *payload* into overlay state, normalize, persist, broadcast."""
        await asyncio.to_thread(self._update_state_and_persist, overlay_id, payload)
        if self._broadcast_callback:
            self._broadcast_callback(overlay_id)

    def update_state_sync(self, overlay_id: str, payload: dict) -> None:
        """Synchronous version of :meth:`update_state`."""
        self._update_state_and_persist(overlay_id, payload)
        if self._broadcast_callback:
            self._broadcast_callback(overlay_id)

    def set_visibility(self, overlay_id: str, show: bool) -> None:
        """Update ``overlay_control.show_main_scoreboard``."""
        def apply(state: dict) -> None:
            state.setdefault("overlay_control", {})["show_main_scoreboard"] = show

        self._mutate_and_persist(overlay_id, apply)
        if self._broadcast_callback:
            self._broadcast_callback(overlay_id)
