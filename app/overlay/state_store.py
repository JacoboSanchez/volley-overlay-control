"""Overlay state management — in-memory cache + runtime-database persistence.

Ported from volleyball-scoreboard-overlay/main.py into a reusable class
so the backend can manage overlay state in-process without an external
overlay server. Each overlay's merged state is one row of
``runtime_overlay_state`` (see :mod:`app.db.runtime`); older releases kept
it in ``data/overlay_state_<hash>.json``, which
:mod:`app.db.runtime_import` imports once at startup.
"""

import asyncio
import copy
import hashlib
import logging
import threading
import time
from collections.abc import Callable, Iterator

from sqlalchemy import delete, select

from app.db.runtime import OverlayRuntimeState, runtime_session
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
    """Return the state a brand-new overlay serves before its first push.

    Built by the real payload builder from a blank match, so even the very
    first WebSocket frame satisfies the published overlay contract
    (:mod:`app.overlay.payload_schema`) instead of a hand-maintained subset
    of it. The neutral placeholder identity ("HOME TEAM" / "AWAY TEAM", the
    ``DEFAULT_TEAM_LOGO``) is kept from the old hand-written default.
    """
    from app.conf import Conf
    from app.customization import Customization
    from app.overlay_payload import build_overlay_payload
    from app.state import State

    conf = Conf()
    conf.sets = best_of_sets
    conf.oid = ""
    state = build_overlay_payload(
        State(),
        dict(Customization.reset_state),
        conf=conf,
        rule_overrides_getter=None,
        logger=logger,
        force_visibility=True,
    )
    default_logo = EnvVarsManager.get_str_env(
        "DEFAULT_TEAM_LOGO", "/static/images/default_volleyball.svg"
    )
    for key, name, short, primary, secondary in (
        ("team_home", "HOME TEAM", "HOM", "#E21836", "#FFFFFF"),
        ("team_away", "AWAY TEAM", "AWA", "#0047AB", "#FFD700"),
    ):
        team = state[key]
        team.update(
            name=name,
            short_name=short,
            color_primary=primary,
            color_secondary=secondary,
            logo_url=default_logo,
        )
        team["set_history"] = {f"set_{i}": 0 for i in range(1, best_of_sets + 1)}
    state["match_info"]["server_time"] = 0.0
    return state


# ---------------------------------------------------------------------------
# OverlayStateStore
# ---------------------------------------------------------------------------


class OverlayStateStore:
    """Manages overlay state with an in-memory cache and database persistence.

    Each overlay's merged render state is one ``runtime_overlay_state`` row
    keyed by its storage key (or a bare legacy overlay id). Reads are served
    from the in-memory context once loaded; every mutation is written back
    in per-overlay order.
    """

    def __init__(self, data_dir: str, templates_dir: str) -> None:
        # Kept for API compatibility (callers and fixtures pass/patch it);
        # nothing is written there any more.
        self._data_dir = data_dir
        self._overlays: dict[str, dict] = {}
        self._lock = threading.RLock()
        self._style_catalog = StyleCatalog(templates_dir, lock=self._lock)
        # Serializes each overlay's mutation -> snapshot -> write sequence
        # without making unrelated overlays wait on one another. These locks
        # are always acquired before ``self._lock``.
        self._persistence_locks: dict[str, threading.Lock] = {}
        self._broadcast_callback: Callable[[str], None] | None = None
        # Maps any accepted URL token (output_key or raw overlay_id) to the
        # real overlay id. Populated lazily by resolve_overlay_id and kept
        # in sync by create/copy/delete.
        self._output_key_cache: dict[str, str] = {}
        self._all_overlays_scanned = False
        # Ids known to have a persisted row. ``overlay_exists`` runs on every
        # model read/save (``ensure_overlay``), so a positive answer is
        # remembered instead of re-queried; create/copy add to it and delete
        # removes from it. Negative answers are never cached.
        self._existing: set[str] = set()
        # Bumped by every delete. ``overlay_exists`` probes the database
        # without the per-overlay lock (``create_overlay`` calls it while
        # holding that lock), so it only caches a positive answer when no
        # delete ran between its probe and its cache write.
        self._delete_generation: dict[str, int] = {}

    def set_broadcast_callback(
        self,
        callback: Callable[[str], None],
    ) -> None:
        """Set the callback invoked after state changes to trigger broadcasts."""
        self._broadcast_callback = callback

    # -- Persistence -------------------------------------------------------

    @staticmethod
    def _sanitize_id(overlay_id: str) -> str:
        """Validate *overlay_id* as a storage identifier.

        Accepts either a bare overlay id (legacy/single-tenant) or a
        per-user storage key ``<user_id>:<oid>`` (:func:`app.overlay_key`).
        Stays the single choke point between caller input and persisted
        rows. Raises ``ValueError`` otherwise.
        """
        if is_valid_skey(overlay_id):
            return overlay_id
        return validate_overlay_id(overlay_id)

    def _read_row(self, overlay_id: str) -> dict | None:
        """Return the persisted state for *overlay_id*, or ``None`` if absent.

        A stored value that is not an object reads as absent (defaults). A
        database *error* propagates: answering "no state" would put default
        state into the in-memory context, and the next mutation would
        persist those defaults over the real row.
        """
        try:
            with runtime_session() as db:
                row = db.get(OverlayRuntimeState, overlay_id)
                state = None if row is None else row.state
        except Exception as exc:
            logger.warning("Failed to load state for '%s': %s", overlay_id, exc)
            raise
        return copy.deepcopy(state) if isinstance(state, dict) else None

    @staticmethod
    def _write_row(overlay_id: str, state: dict) -> None:
        with runtime_session() as db:
            db.merge(
                OverlayRuntimeState(
                    store_key=overlay_id, state=state, updated_at=time.time(),
                )
            )

    @staticmethod
    def _insert_row(overlay_id: str, state: dict) -> bool:
        """INSERT a new row; ``False`` when one already exists.

        ``create_overlay`` uses this instead of :meth:`_write_row` so it can
        never overwrite a real row — not when an existence probe failed
        transiently, and not when another process created it first.
        """
        from sqlalchemy.exc import IntegrityError

        try:
            with runtime_session() as db:
                db.add(
                    OverlayRuntimeState(
                        store_key=overlay_id, state=state, updated_at=time.time(),
                    )
                )
        except IntegrityError:
            return False
        return True

    @staticmethod
    def _stamp_meta(state: dict, overlay_id: str) -> dict:
        """Inject ``_meta.overlay_id`` so a row is self-describing.

        Kept from the file era, where filenames were hashes; exported or
        hand-inspected state still names its overlay. Returns *state*.
        """
        meta = state.setdefault("_meta", {})
        meta["overlay_id"] = overlay_id
        return state

    def load_persisted_state(self, overlay_id: str) -> dict:
        safe_id = self._sanitize_id(overlay_id)
        state = self._read_row(safe_id)
        return state if state is not None else get_default_state()

    async def load_persisted_state_async(self, overlay_id: str) -> dict:
        return await asyncio.to_thread(self.load_persisted_state, overlay_id)

    def _save_persisted_state_unlocked(self, overlay_id: str, state: dict) -> None:
        """Persist *state* while the caller holds the overlay's write lock."""
        safe_id = self._sanitize_id(overlay_id)
        self._stamp_meta(state, safe_id)
        try:
            self._write_row(safe_id, state)
        except Exception as exc:
            # Best-effort like the file writes it replaced: a failed write
            # leaves the in-memory state authoritative until the next save.
            logger.warning("Failed to save state for '%s': %s", overlay_id, exc)
            return
        with self._lock:
            self._existing.add(safe_id)

    def save_persisted_state(self, overlay_id: str, state: dict) -> None:
        with self._get_persistence_lock(overlay_id):
            self._save_persisted_state_unlocked(overlay_id, state)

    async def save_persisted_state_async(self, overlay_id: str, state: dict) -> None:
        await asyncio.to_thread(self.save_persisted_state, overlay_id, state)

    def _get_persistence_lock(self, overlay_id: str) -> threading.Lock:
        """Return the stable per-overlay lock used to order snapshots."""
        with self._lock:
            return self._persistence_locks.setdefault(overlay_id, threading.Lock())

    def _row_exists(self, overlay_id: str) -> bool:
        """Probe for a row. An error reads as "absent" for the bool contract;
        that is safe because creation is insert-only (:meth:`_insert_row`)."""
        try:
            with runtime_session() as db:
                return db.get(OverlayRuntimeState, overlay_id) is not None
        except Exception as exc:
            logger.warning("Failed to probe state for '%s': %s", overlay_id, exc)
            return False

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
        """Check whether persisted state exists for *overlay_id*.

        Returns False for ids that fail the sanitizer so the public contract
        (a bool) is preserved — callers probing with arbitrary user input
        get the same "no such overlay" answer they'd get for a well-formed
        id that happens to not exist.
        """
        try:
            safe_id = self._sanitize_id(overlay_id)
        except ValueError:
            return False
        with self._lock:
            if safe_id in self._existing:
                return True
            generation = self._delete_generation.get(safe_id, 0)
        if not self._row_exists(safe_id):
            return False
        with self._lock:
            # A delete that landed after the probe makes its answer stale;
            # report it, but do not cache it.
            if self._delete_generation.get(safe_id, 0) == generation:
                self._existing.add(safe_id)
        return True

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
        re-scanning the table.
        """
        with self._lock:
            cached = self._output_key_cache.get(token)
            if cached is not None:
                return cached
            if self._all_overlays_scanned:
                return None
            self._populate_cache_locked()
            return self._output_key_cache.get(token)

    def _iter_persisted_ids(self) -> Iterator[str]:
        """Yield every persisted overlay id, skipping malformed keys.

        A database error propagates, so a failed scan is never mistaken for
        an empty table (see :meth:`_populate_cache_locked`).
        """
        with runtime_session() as db:
            keys = list(db.scalars(select(OverlayRuntimeState.store_key)))
        for oid in keys:
            if is_valid_overlay_id(oid) or is_valid_skey(oid):
                yield oid
            else:
                logger.warning("Skipping overlay state with invalid key %r", oid)

    def _populate_cache_locked(self) -> None:
        """Scan the persisted ids once and index every overlay by both
        its raw id and its output key. Caller must hold ``self._lock``.
        """
        if self._all_overlays_scanned:
            return
        try:
            ids = list(self._iter_persisted_ids())
        except Exception as exc:
            # Leave the flag unset so the next lookup retries the scan.
            logger.warning("Failed to list overlay states: %s", exc)
            return
        for oid in ids:
            self._output_key_cache[oid] = oid
            self._output_key_cache[self.get_output_key(oid)] = oid
        self._all_overlays_scanned = True

    # -- Available styles --------------------------------------------------

    def get_available_styles_list(self) -> list[str]:
        return self._style_catalog.get_available_styles_list()

    def get_renderable_styles(self) -> list[str]:
        return self._style_catalog.get_renderable_styles()

    # -- Style capabilities ------------------------------------------------

    def get_style_capabilities(self) -> dict[str, dict[str, bool | str]]:
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
    def _style_capabilities(self) -> dict[str, dict[str, bool | str]] | None:
        return self._style_catalog._style_capabilities

    @_style_capabilities.setter
    def _style_capabilities(
        self,
        value: dict[str, dict[str, bool | str]] | None,
    ) -> None:
        self._style_catalog._style_capabilities = value

    # -- CRUD --------------------------------------------------------------

    def create_overlay(self, overlay_id: str) -> bool:
        """Create a new overlay with default state.  Returns True if created."""
        try:
            safe_id = self._sanitize_id(overlay_id)
        except ValueError:
            logger.warning("create_overlay rejected invalid id: %r", overlay_id)
            return False
        with self._get_persistence_lock(safe_id):
            # Hold the overlay's write lock across the existence check and
            # write so two concurrent first-touches cannot both create
            # default state.
            if self.overlay_exists(safe_id):
                return False
            state = self._stamp_meta(get_default_state(), safe_id)
            try:
                created = self._insert_row(safe_id, state)
            except Exception as exc:
                logger.warning("Failed to create state for '%s': %s", safe_id, exc)
                return False
            with self._lock:
                self._existing.add(safe_id)
            if not created:
                return False
            with self._lock:
                self._output_key_cache[safe_id] = safe_id
                self._output_key_cache[self.get_output_key(safe_id)] = safe_id
        logger.info("Overlay '%s' created", safe_id)
        return True

    def ensure_overlay(self, overlay_id: str) -> None:
        """Create the overlay if it does not already exist."""
        if not self.overlay_exists(overlay_id):
            self.create_overlay(overlay_id)

    def delete_overlay(self, overlay_id: str) -> bool:
        """Delete an overlay's persisted state and in-memory context."""
        try:
            safe_id = self._sanitize_id(overlay_id)
        except ValueError:
            logger.warning("delete_overlay rejected invalid id: %r", overlay_id)
            return False
        existed = False
        with self._get_persistence_lock(safe_id):
            try:
                with runtime_session() as db:
                    result = db.execute(
                        delete(OverlayRuntimeState).where(
                            OverlayRuntimeState.store_key == safe_id
                        )
                    )
                    existed = bool(getattr(result, "rowcount", 0))
            except Exception as exc:
                logger.warning("Failed to delete state for '%s': %s", safe_id, exc)
            with self._lock:
                self._existing.discard(safe_id)
                self._delete_generation[safe_id] = (
                    self._delete_generation.get(safe_id, 0) + 1
                )
                if safe_id in self._overlays:
                    del self._overlays[safe_id]
                    existed = True
                self._output_key_cache.pop(safe_id, None)
                self._output_key_cache.pop(self.get_output_key(safe_id), None)
        if existed:
            logger.info("Overlay '%s' deleted", safe_id)
        return existed

    def list_overlays(self) -> list:
        """Return a list of ``{id, output_key}`` for all persisted overlays."""
        entries = [
            {"id": oid, "output_key": self.get_output_key(oid)}
            for oid in self._iter_persisted_ids()
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
