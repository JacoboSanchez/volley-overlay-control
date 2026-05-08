"""On-disk catalogue for overlay configuration presets.

A *preset* is a named, scope-tagged subset of an overlay's state that
the operator saves once and applies anywhere. The catalogue is global
(presets are not per-OID) so the same "Real Madrid as home" preset
can be applied to any overlay that needs it.

Files live at ``data/presets/preset_<sha256(slug)[:20]>.json``. The
hex-only basename keeps user-supplied names from flowing into
filesystem paths (same security pattern ``OverlayStateStore`` uses
for overlay state). The original name plus the slug are recorded in
the JSON payload's ``_meta`` block so listings and lookups can
recover them.

Concurrency: a single process-wide :class:`threading.RLock` guards
every read and write. Presets are an admin surface — write rate is
operator-keystroke, never hot-path — so the simpler global lock is
preferable to the per-slug pool ``action_log`` uses for game events.

All I/O is best-effort: filesystem failures are logged but never
propagate, so a busted ``data/presets`` directory cannot wedge a
live match by surfacing a 500 from the admin handler.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import tempfile
import threading
import time

from app.constants import PRESETS_MAX_NAME_LEN, PRESETS_MAX_RECORDS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Slug + filename helpers
# ---------------------------------------------------------------------------

# A slug is at most ``PRESETS_MAX_NAME_LEN`` characters of lowercase
# alphanumerics plus dashes. The hash-based filename means the slug
# never reaches the filesystem directly, but keeping it well-formed
# helps the admin UI render legible URLs and JSON.
_SLUG_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
_FILENAME_HASH_LEN = 20
_HASHED_FILENAME_PATTERN = re.compile(
    r"^preset_[0-9a-f]{" + str(_FILENAME_HASH_LEN) + r"}\.json$",
)


def slugify(name: str) -> str:
    """Return a filesystem-safe slug for *name*.

    Lowercase ASCII alphanumerics plus dashes; runs of any other
    character collapse to a single dash; leading and trailing dashes
    trimmed; empty result raises ``ValueError`` so the caller surfaces
    a 400 instead of writing an unaddressable preset. Length is
    clamped to ``PRESETS_MAX_NAME_LEN`` to keep slugs manageable in
    URLs and JSON.
    """
    if not isinstance(name, str):
        raise ValueError("Preset name must be a string.")
    # Lower + ASCII fold via NFKD would catch accented characters
    # too, but the operator-facing audit trail benefits from keeping
    # the original ``name`` separate from the slug. We just normalise
    # what makes a valid filesystem-and-URL-safe identifier.
    cleaned = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    cleaned = cleaned[:max(1, PRESETS_MAX_NAME_LEN)]
    if not cleaned or _SLUG_PATTERN.match(cleaned) is None:
        raise ValueError(f"Cannot derive a valid slug from {name!r}.")
    return cleaned


def _data_dir() -> str:
    """Return the on-disk preset directory."""
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(base, "..", "..", "data", "presets"))


def _hashed_basename(slug: str) -> str:
    digest = hashlib.sha256(slug.encode("utf-8")).hexdigest()[:_FILENAME_HASH_LEN]
    return f"preset_{digest}.json"


def _path(slug: str) -> str:
    """Return the on-disk path for a preset *slug*. Caller must have validated."""
    return os.path.join(_data_dir(), _hashed_basename(slug))


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

_lock = threading.RLock()


def _validate_name(name: str) -> str:
    if not isinstance(name, str):
        raise ValueError("Preset name must be a string.")
    name = name.strip()
    if not name:
        raise ValueError("Preset name is required.")
    if len(name) > PRESETS_MAX_NAME_LEN:
        raise ValueError(
            f"Preset name exceeds {PRESETS_MAX_NAME_LEN} characters.",
        )
    return name


def _serialize(preset: dict) -> bytes:
    return (json.dumps(preset, ensure_ascii=False) + "\n").encode("utf-8")


def _write_atomic_locked(path: str, payload: dict) -> None:
    """Tempfile + ``os.replace`` write while holding ``_lock``."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(_serialize(payload))
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _read_payload(path: str) -> dict | None:
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Skipping unreadable preset '%s': %s", path, exc)
        return None
    return payload if isinstance(payload, dict) else None


def _build_record(
    name: str, slug: str, scopes: list[str], snapshots: dict[str, dict],
) -> dict:
    return {
        "_meta": {
            "name": name,
            "slug": slug,
            "created_at": time.time(),
        },
        "scopes": list(scopes),
        "snapshots": dict(snapshots),
    }


class PresetExists(Exception):
    """A preset with the requested slug is already on disk."""


class PresetNotFound(Exception):
    """No preset matches the requested slug."""


class PresetCatalogueFull(Exception):
    """The catalogue would exceed ``PRESETS_MAX_RECORDS``."""


def create(
    name: str, scopes: list[str], snapshots: dict[str, dict],
) -> dict:
    """Persist a new preset and return the saved record.

    Raises:
      * ``ValueError`` for invalid names / unknown scopes.
      * :class:`PresetExists` when the derived slug collides with an
        existing preset (caller can offer a rename / overwrite).
      * :class:`PresetCatalogueFull` when the catalogue is at its cap.
    """
    name = _validate_name(name)
    slug = slugify(name)
    path = _path(slug)
    with _lock:
        if os.path.exists(path):
            raise PresetExists(slug)
        # Cheap cap check — counts the directory once on create. The
        # admin surface is low-volume; an O(n) listdir per save is
        # fine and simpler than maintaining a counter.
        if _count_locked() >= PRESETS_MAX_RECORDS:
            raise PresetCatalogueFull(
                f"Preset catalogue is full ({PRESETS_MAX_RECORDS} entries). "
                f"Delete unused presets before saving more.",
            )
        record = _build_record(name, slug, scopes, snapshots)
        _write_atomic_locked(path, record)
    logger.info("Preset '%s' (slug=%s) created", name, slug)
    return record


def read(slug: str) -> dict:
    """Return the preset record for *slug*. Raises :class:`PresetNotFound`."""
    if _SLUG_PATTERN.match(slug) is None:
        raise PresetNotFound(slug)
    with _lock:
        payload = _read_payload(_path(slug))
    if payload is None:
        raise PresetNotFound(slug)
    return payload


def delete(slug: str) -> bool:
    """Remove a preset. Returns ``True`` when a file was removed."""
    if _SLUG_PATTERN.match(slug) is None:
        return False
    with _lock:
        path = _path(slug)
        if not os.path.exists(path):
            return False
        try:
            os.remove(path)
        except OSError as exc:
            logger.warning("Failed to delete preset '%s': %s", slug, exc)
            return False
    logger.info("Preset slug=%s deleted", slug)
    return True


def list_all() -> list[dict]:
    """Return every preset record, ordered by name (case-insensitive)."""
    with _lock:
        records = list(_iter_payloads_locked())
    records.sort(key=lambda r: (r.get("_meta", {}).get("name") or "").lower())
    return records


def import_payload(payload: dict, *, override_name: str | None = None) -> dict:
    """Persist a preset record sourced from an external JSON document.

    The payload must already be the on-disk schema produced by
    :func:`create` or :func:`export_payload`. Slug collisions are
    resolved by appending ``-2``, ``-3``... up to ``-99`` so reimport
    of the same export does not silently overwrite the existing
    catalogue entry. ``override_name`` (when supplied by the operator)
    wins over whatever ``_meta.name`` carries — useful when the same
    preset is imported as a variant.
    """
    if not isinstance(payload, dict):
        raise ValueError("Preset import payload must be a JSON object.")
    snapshots = payload.get("snapshots") or {}
    scopes = payload.get("scopes") or []
    if not isinstance(snapshots, dict) or not isinstance(scopes, list):
        raise ValueError("Preset payload is missing 'scopes' / 'snapshots'.")
    name_source = override_name or payload.get("_meta", {}).get("name", "")
    name = _validate_name(name_source)
    base_slug = slugify(name)
    slug = base_slug
    suffix = 1
    with _lock:
        while os.path.exists(_path(slug)):
            suffix += 1
            if suffix > 99:
                raise PresetExists(base_slug)
            slug = f"{base_slug}-{suffix}"
            # Re-validate the (longer) candidate slug; the suffix
            # might push the original past ``MAX_NAME_LEN``.
            if len(slug) > PRESETS_MAX_NAME_LEN:
                raise ValueError(
                    "Preset name too long to disambiguate on import.",
                )
        if _count_locked() >= PRESETS_MAX_RECORDS:
            raise PresetCatalogueFull(
                f"Preset catalogue is full ({PRESETS_MAX_RECORDS} entries).",
            )
        record = _build_record(name, slug, list(scopes), dict(snapshots))
        _write_atomic_locked(_path(slug), record)
    logger.info("Preset '%s' (slug=%s) imported", name, slug)
    return record


def export_payload(slug: str) -> dict:
    """Return the on-disk record for *slug* as a portable JSON dict.

    The returned dict is identical to what :func:`import_payload`
    accepts — round-trip is guaranteed by sharing the schema.
    """
    return read(slug)


def count() -> int:
    """Return the current number of presets on disk."""
    with _lock:
        return _count_locked()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _iter_payloads_locked():
    directory = _data_dir()
    if not os.path.isdir(directory):
        return
    for filename in os.listdir(directory):
        if not _HASHED_FILENAME_PATTERN.fullmatch(filename):
            continue
        path = os.path.join(directory, filename)
        payload = _read_payload(path)
        if payload is None:
            continue
        yield payload


def _count_locked() -> int:
    n = 0
    directory = _data_dir()
    if not os.path.isdir(directory):
        return 0
    for filename in os.listdir(directory):
        if _HASHED_FILENAME_PATTERN.fullmatch(filename):
            n += 1
    return n
