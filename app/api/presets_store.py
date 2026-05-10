"""On-disk catalogue for operator-curated configuration presets.

A *preset* is a named subset of the operator's flat customization model
(``Team 1 Color``, ``Height``, …). The operator captures the parts of
the current overlay configuration they care about and applies them
again later from the React control panel. There is no admin gate: any
caller with the API key can list, create, and delete entries.

Files live at ``data/presets/preset_<sha256(slug)[:20]>.json``. The
hex-only basename keeps user-supplied names from flowing into
filesystem paths (same security pattern :class:`OverlayStateStore`
uses for overlay state). The original name plus the slug are recorded
in the JSON payload's ``_meta`` block so listings and lookups can
recover them.

Concurrency: a single process-wide :class:`threading.RLock` guards
every read and write. Write rate is operator-keystroke; the simpler
global lock is preferable to the per-slug pool ``action_log`` uses for
game events.

All I/O is best-effort: filesystem failures are logged but never
propagate, so a busted ``data/presets`` directory cannot wedge a live
match by surfacing a 500 from the API handler.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import threading
import time
from typing import Any

from app.api._persistence_paths import DEFAULT_HASH_LEN, hashed_filename
from app.api._persistence_paths import data_dir as _shared_data_dir
from app.api.preset_categories import categories_for_keys, filter_to_known
from app.constants import PRESETS_MAX_NAME_LEN, PRESETS_MAX_RECORDS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Slug + filename helpers
# ---------------------------------------------------------------------------

# A slug is lowercase ASCII alphanumerics plus dashes, beginning and
# ending with an alphanumeric.
_SLUG_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")
_FILENAME_HASH_LEN = DEFAULT_HASH_LEN
_HASHED_FILENAME_PATTERN = re.compile(
    r"^preset_[0-9a-f]{" + str(_FILENAME_HASH_LEN) + r"}\.json$",
)

# Reserved for env-driven system presets surfaced by the listing
# endpoint alongside user-saved records. Disk storage never uses this
# prefix; ``slugify`` rejects user names that resolve to it so a
# malicious caller can't shadow a system entry by saving a collision.
SYSTEM_SLUG_PREFIX = "system-"


def slugify(name: str, *, check_reserved: bool = True) -> str:
    """Return a filesystem-safe slug for *name*.

    Lowercase ASCII alphanumerics plus dashes; runs of any other
    character collapse to a single dash; leading and trailing dashes
    trimmed; empty result raises ``ValueError`` so the caller surfaces
    a 400 instead of writing an unaddressable preset. Length is clamped
    to ``PRESETS_MAX_NAME_LEN`` to keep slugs manageable in URLs and
    JSON. Names that resolve to the reserved ``system-`` prefix are
    rejected for the same reason.

    Pass ``check_reserved=False`` from the system-preset loader, which
    always prepends ``SYSTEM_SLUG_PREFIX`` to the result anyway, so a
    theme literally named "System Dark" still yields an addressable
    ``system-system-dark`` slug instead of being silently dropped.
    User-facing callers must keep the default to preserve the
    reservation invariant.
    """
    if not isinstance(name, str):
        raise ValueError("Preset name must be a string.")
    cleaned = re.sub(r"[^a-z0-9]+", "-", name.strip().lower())
    cleaned = cleaned[: max(1, PRESETS_MAX_NAME_LEN)].strip("-")
    if not cleaned or _SLUG_PATTERN.match(cleaned) is None:
        raise ValueError(f"Cannot derive a valid slug from {name!r}.")
    if check_reserved and cleaned.startswith(SYSTEM_SLUG_PREFIX):
        raise ValueError(
            f"Preset slug {cleaned!r} uses the reserved "
            f"{SYSTEM_SLUG_PREFIX!r} prefix.",
        )
    return cleaned


def _data_dir() -> str:
    # Wrapper kept so tests can monkeypatch this attribute.
    return _shared_data_dir("presets")


def _hashed_basename(slug: str) -> str:
    return hashed_filename("preset_", slug)


def _path(slug: str) -> str:
    return os.path.join(_data_dir(), _hashed_basename(slug))


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

_lock = threading.RLock()


class PresetExists(Exception):
    """A preset with the requested slug is already on disk."""


class PresetNotFound(Exception):
    """No preset matches the requested slug."""


class PresetCatalogueFull(Exception):
    """The catalogue would exceed ``PRESETS_MAX_RECORDS``."""


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


def _serialize(record: dict) -> bytes:
    return (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8")


def _write_atomic_locked(path: str, payload: dict) -> None:
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


def _build_record(name: str, slug: str, values: dict[str, Any]) -> dict:
    # ``categories`` is derived from the keys in ``values`` so the
    # field can never drift out of sync with the actual content.
    return {
        "_meta": {
            "name": name,
            "slug": slug,
            "created_at": time.time(),
        },
        "categories": categories_for_keys(values.keys()),
        "values": dict(values),
    }


def create(name: str, values: dict[str, Any]) -> dict:
    """Persist a new preset and return the saved record.

    *values* is a flat dict of allow-listed customization keys
    (``Team 1 Color``, ``Height``, …). Unknown keys are dropped before
    persistence so the on-disk record only ever carries fields the
    operator-side endpoint can apply.

    Raises:
      * ``ValueError`` for invalid names / empty values.
      * :class:`PresetExists` when the derived slug collides with an
        existing preset.
      * :class:`PresetCatalogueFull` when the catalogue is at its cap.
    """
    name = _validate_name(name)
    slug = slugify(name)
    cleaned = filter_to_known(values)
    if not cleaned:
        raise ValueError(
            "Preset must contain at least one supported customization key.",
        )
    path = _path(slug)
    with _lock:
        if os.path.exists(path):
            raise PresetExists(slug)
        if _count_locked() >= PRESETS_MAX_RECORDS:
            raise PresetCatalogueFull(
                f"Preset catalogue is full ({PRESETS_MAX_RECORDS} entries). "
                f"Delete unused presets before saving more.",
            )
        record = _build_record(name, slug, cleaned)
        _write_atomic_locked(path, record)
    logger.info("Preset '%s' (slug=%s, %d keys)", name, slug, len(cleaned))
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


def count() -> int:
    with _lock:
        return _count_locked()


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
