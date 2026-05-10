"""Shared helpers for per-OID JSON persistence under ``<repo>/data``.

Several modules (``session_persistence``, ``action_log``, ``match_archive``,
``presets_store``, ``overlay.state_store``) historically reimplemented
the same three primitives:

  * resolve the data directory anchored at the repo root,
  * hash a key (OID, slug, …) into a deterministic filename,
  * atomically write a JSON document via ``mkstemp`` + ``os.replace``.

Centralising them avoids subtle drift between modules and lets new
persistence callers reuse the same on-disk convention.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from typing import Any

# Hash-prefix length used across all per-OID/slug filenames. Kept here
# so callers cannot pick a different value by accident.
DEFAULT_HASH_LEN = 20


def data_dir(*parts: str) -> str:
    """Return ``<repo-root>/data[/parts...]`` as a normalized path.

    The repo root is ``app/api/_persistence_paths.py`` -> ``app/api/`` ->
    ``app/`` -> repo. Mirrors the legacy per-module ``_data_dir`` helpers.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "..", "data", *parts))


def hashed_filename(
    prefix: str,
    value: str,
    suffix: str = ".json",
    *,
    hash_len: int = DEFAULT_HASH_LEN,
) -> str:
    """Return ``{prefix}{sha256(value)[:hash_len]}{suffix}``."""
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:hash_len]
    return f"{prefix}{digest}{suffix}"


def atomic_write_json(path: str, payload: Any, *, ensure_ascii: bool = True) -> None:
    """Atomically write *payload* as JSON to *path*.

    Creates the parent directory if needed, writes via ``mkstemp`` in
    the same directory (so ``os.replace`` is atomic across the rename),
    and unlinks the temp file on any exception before re-raising. The
    caller decides how to log/swallow exceptions.
    """
    parent = os.path.dirname(path)
    os.makedirs(parent, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=ensure_ascii)
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
