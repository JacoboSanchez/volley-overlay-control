"""Persistent storage for manageable predefined overlays.

Overlays declared through the admin page are stored in
``data/managed_overlays.json`` so they survive process restarts. This is a
separate namespace from the read-only ``PREDEFINED_OVERLAYS`` env var —
the public ``/api/v1/overlays`` endpoint merges both sources, but only
managed overlays can be created, updated or deleted at runtime.
"""

import json
import logging
import os
import tempfile
import threading
from typing import Dict, List, Optional

logger = logging.getLogger("OverlaysStore")


_DEFAULT_DATA_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "data"
)


class OverlayNotFoundError(KeyError):
    """Raised when a managed overlay does not exist."""


class OverlayConflictError(KeyError):
    """Raised when a create/rename would duplicate an existing overlay."""


class OverlaysStore:
    """Thread-safe JSON-backed store for managed overlays.

    The on-disk format is a JSON object keyed by overlay name:

    .. code-block:: json

        {
            "My overlay": {
                "control": "<control token or URL>",
                "output": "<optional output token/URL>",
                "allowed_users": ["user1", "user2"]
            }
        }
    """

    FILENAME = "managed_overlays.json"

    def __init__(self, data_dir: Optional[str] = None):
        self._data_dir = os.path.abspath(data_dir or _DEFAULT_DATA_DIR)
        self._path = os.path.join(self._data_dir, self.FILENAME)
        self._lock = threading.RLock()
        self._overlays: Dict[str, dict] = {}
        self._loaded = False

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            self._overlays = self._read_from_disk()
            self._loaded = True

    def _read_from_disk(self) -> Dict[str, dict]:
        if not os.path.isfile(self._path):
            return {}
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not load %s (%s) — starting empty.", self._path, exc)
            return {}
        if not isinstance(data, dict):
            logger.warning("%s is not a JSON object — ignoring.", self._path)
            return {}
        # Drop entries that do not conform to the schema.
        return {
            name: self._normalise(entry)
            for name, entry in data.items()
            if isinstance(name, str) and name.strip() and isinstance(entry, dict)
        }

    def _write_to_disk(self) -> None:
        os.makedirs(self._data_dir, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            prefix=".managed_overlays_", suffix=".tmp", dir=self._data_dir
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self._overlays, fh, indent=2, ensure_ascii=False)
            os.replace(tmp_path, self._path)
        except Exception:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            raise

    # ------------------------------------------------------------------
    # Normalisation
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise(entry: dict) -> dict:
        """Return a sanitised copy of *entry* with the expected shape."""
        control = entry.get("control")
        if not isinstance(control, str):
            control = ""
        result: dict = {"control": control.strip()}
        output = entry.get("output")
        if isinstance(output, str) and output.strip():
            result["output"] = output.strip()
        allowed = entry.get("allowed_users")
        if isinstance(allowed, list):
            cleaned = [u for u in allowed if isinstance(u, str) and u.strip()]
            if cleaned:
                result["allowed_users"] = cleaned
        return result

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list(self) -> List[dict]:
        """Return managed overlays as a list of ``{name, ...}`` dicts.

        Each entry is freshly normalised so callers can mutate the returned
        dicts or nested lists without corrupting the store's internal state.
        """
        self._ensure_loaded()
        with self._lock:
            return [
                {"name": name, **self._normalise(entry)}
                for name, entry in sorted(self._overlays.items(), key=lambda kv: kv[0].lower())
            ]

    def as_dict(self) -> Dict[str, dict]:
        """Return a defensive copy of the stored overlays keyed by name."""
        self._ensure_loaded()
        with self._lock:
            return {name: self._normalise(entry) for name, entry in self._overlays.items()}

    def get(self, name: str) -> Optional[dict]:
        self._ensure_loaded()
        with self._lock:
            entry = self._overlays.get(name)
            return self._normalise(entry) if entry is not None else None

    def create(self, name: str, entry: dict) -> dict:
        name = (name or "").strip()
        if not name:
            raise ValueError("Overlay name is required")
        normalised = self._normalise(entry)
        if not normalised["control"]:
            raise ValueError("Overlay control token/URL is required")
        self._ensure_loaded()
        with self._lock:
            if name in self._overlays:
                raise OverlayConflictError(f"Overlay '{name}' already exists")
            self._overlays[name] = normalised
            self._write_to_disk()
            return {"name": name, **self._normalise(normalised)}

    def update(self, name: str, entry: dict, *, new_name: Optional[str] = None) -> dict:
        self._ensure_loaded()
        with self._lock:
            if name not in self._overlays:
                raise OverlayNotFoundError(f"Overlay '{name}' not found")
            normalised = self._normalise(entry)
            if not normalised["control"]:
                raise ValueError("Overlay control token/URL is required")
            target = (new_name or name).strip()
            if not target:
                raise ValueError("Overlay name is required")
            if target != name and target in self._overlays:
                raise OverlayConflictError(f"Overlay '{target}' already exists")
            if target != name:
                del self._overlays[name]
            self._overlays[target] = normalised
            self._write_to_disk()
            return {"name": target, **self._normalise(normalised)}

    def delete(self, name: str) -> None:
        self._ensure_loaded()
        with self._lock:
            if name not in self._overlays:
                raise OverlayNotFoundError(f"Overlay '{name}' not found")
            del self._overlays[name]
            self._write_to_disk()

    # ------------------------------------------------------------------
    # Testing helpers
    # ------------------------------------------------------------------

    def _reset_for_tests(self, data_dir: Optional[str] = None) -> None:
        """Reset in-memory state and optionally repoint the storage path."""
        with self._lock:
            if data_dir is not None:
                self._data_dir = os.path.abspath(data_dir)
                self._path = os.path.join(self._data_dir, self.FILENAME)
            self._overlays = {}
            self._loaded = False


# Module-level singleton — used by the admin router and by the public
# ``/api/v1/overlays`` endpoint to merge managed overlays into the list.
managed_overlays_store = OverlaysStore()
