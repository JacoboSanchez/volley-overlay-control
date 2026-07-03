"""Hosted team-icon library: image processing, storage, and CRUD.

Icons live in two places that must stay consistent:

  * a row in the ``icons`` table (name, dimensions, ownership), and
  * a WebP file under ``data/media/icons/`` served from the public
    ``/media`` mount (OBS browser sources carry no cookies, so the
    files are deliberately unauthenticated — same posture as
    ``/static``).

Every input image — whatever the client sends — is decoded with
Pillow behind a decompression-bomb guard, shrunk to fit
``ICONS_MAX_DIM`` on its longest side, and re-encoded to WebP, so the
stored footprint is bounded server-side rather than trusted from the
upload. The filename embeds a content hash (cache-busting: the URL
never changes meaning) plus a random suffix (unique per row, so
deleting a row can always unlink its file without refcounting).

Teams reference icons only through ``Team.icon_url`` strings; deleting
an icon clears referencing teams by exact URL match and reports how
many were touched.
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
import secrets
import tempfile
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import event, func, select, update
from sqlalchemy.orm import Session

from app.api._persistence_paths import data_dir
from app.constants import (
    ICONS_IMPORT_TIMEOUT_SECONDS,
    ICONS_MAX_DIM,
    ICONS_MAX_PER_USER,
    ICONS_MAX_PIXELS,
    ICONS_MAX_STORED_BYTES,
    ICONS_MAX_UPLOAD_BYTES,
    ICONS_WEBP_QUALITY,
)
from app.db.models.icon import Icon
from app.db.models.team import Team
from app.net_guard import GuardedFetchError, fetch_guarded

logger = logging.getLogger(__name__)

# Public URL prefix the /media mount serves icons from. Single source
# for the URL shape — routes, deletion matching, and the batch import
# idempotence check all derive from it.
ICONS_URL_PREFIX = "/media/icons/"

# Feed Pillow's decompression-bomb guard from our own knob. Module
# level so it applies to every decode in the process, including any
# future non-icon image handling.
Image.MAX_IMAGE_PIXELS = ICONS_MAX_PIXELS

# Formats we accept after sniffing the actual bytes (never the client
# Content-Type). SVG is deliberately absent in v1: Pillow cannot decode
# it and passing XML through unrasterized would open a script-injection
# surface.
_ACCEPTED_FORMATS = {"PNG", "JPEG", "WEBP", "GIF"}

# Quality ladder: retry the WebP encode at decreasing quality until the
# output fits ICONS_MAX_STORED_BYTES. A 512x512 WebP virtually never
# exceeds 512 KiB even at q82 — the ladder is belt-and-braces.
_QUALITY_LADDER_FLOOR = (70, 55, 40)

# Must match the ``icons.name`` column width (String(120)).
_MAX_NAME_LEN = 120


class IconError(ValueError):
    """A caller-fixable icon error (bad image, duplicate, quota, missing)."""


def icons_dir() -> str:
    """Directory the icon files live in (monkeypatchable in tests)."""
    return data_dir("media", "icons")


def icon_public_url(filename: str) -> str:
    return f"{ICONS_URL_PREFIX}{filename}"


@dataclass(frozen=True)
class ProcessedIcon:
    content: bytes
    width: int
    height: int


def process_icon_upload(raw: bytes) -> ProcessedIcon:
    """Decode, shrink, and re-encode *raw* image bytes to bounded WebP.

    Raises :class:`IconError` for anything the uploader can fix: not an
    image, an unsupported format, a decompression bomb, or an image
    that will not compress under the stored-size cap.
    """
    if len(raw) > ICONS_MAX_UPLOAD_BYTES:
        raise IconError(
            f"Image is too large (max {ICONS_MAX_UPLOAD_BYTES // (1024 * 1024)} MB)."
        )
    head = raw[:512].lstrip().lower()
    if head.startswith(b"<?xml") or b"<svg" in head:
        raise IconError("SVG images are not supported — upload PNG, JPEG, WebP or GIF.")
    try:
        with Image.open(io.BytesIO(raw)) as img:
            fmt = (img.format or "").upper()
            if fmt not in _ACCEPTED_FORMATS:
                raise IconError(
                    f"Unsupported image format {fmt or 'unknown'!r} — "
                    "upload PNG, JPEG, WebP or GIF."
                )
            # Animated inputs are flattened to their first frame (v1).
            img.seek(0)
            # Bake EXIF rotation in, then normalize palette/CMYK/L modes;
            # RGBA keeps transparency and WebP encodes it natively.
            img = ImageOps.exif_transpose(img)
            img = img.convert("RGBA")
            # thumbnail() preserves aspect ratio and never upscales.
            img.thumbnail((ICONS_MAX_DIM, ICONS_MAX_DIM), Image.Resampling.LANCZOS)
            for quality in (ICONS_WEBP_QUALITY, *_QUALITY_LADDER_FLOOR):
                buf = io.BytesIO()
                img.save(buf, format="WEBP", quality=quality, method=6)
                content = buf.getvalue()
                if len(content) <= ICONS_MAX_STORED_BYTES:
                    return ProcessedIcon(content, img.width, img.height)
            raise IconError("Image does not compress under the stored-size limit.")
    except Image.DecompressionBombError as exc:
        raise IconError("Image has too many pixels.") from exc
    except UnidentifiedImageError as exc:
        raise IconError("File is not a recognizable image.") from exc


def _store_file(content: bytes) -> str:
    """Write *content* into :func:`icons_dir` and return the filename.

    Same temp-then-``os.replace`` dance as ``atomic_write_json`` so a
    crash mid-write never leaves a truncated file behind the immutable
    ``/media`` cache headers.
    """
    filename = (
        f"{hashlib.sha256(content).hexdigest()[:20]}-{secrets.token_hex(4)}.webp"
    )
    directory = icons_dir()
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(content)
        # mkstemp creates 0600; these files are public by design (the /media
        # mount, or a reverse proxy serving the directory straight from disk
        # under a different user), so grant world-read explicitly.
        os.chmod(tmp_path, 0o644)
        os.replace(tmp_path, os.path.join(directory, filename))
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    return filename


def _unlink_file(filename: str) -> None:
    """Best-effort removal of an icon file (row is already gone)."""
    try:
        os.unlink(os.path.join(icons_dir(), filename))
    except OSError:
        logger.warning("Could not remove icon file %s", filename, exc_info=True)


# ---- queries ----------------------------------------------------------------


def list_global(db: Session) -> list[Icon]:
    return list(
        db.execute(
            select(Icon).where(Icon.is_global.is_(True)).order_by(Icon.name)
        ).scalars().all()
    )


def list_mine(db: Session, user_id: int) -> list[Icon]:
    return list(
        db.execute(
            select(Icon).where(Icon.owner_user_id == user_id).order_by(Icon.name)
        ).scalars().all()
    )


def user_icon_count(db: Session, user_id: int) -> int:
    return int(
        db.execute(
            select(func.count()).select_from(Icon).where(Icon.owner_user_id == user_id)
        ).scalar_one()
    )


def get_scoped(db: Session, icon_id: int, *, user_id: int | None) -> Icon | None:
    """Return the icon iff it belongs to the given scope.

    ``user_id=None`` selects the global scope (admin routes); a user id
    selects that user's personal icons. Cross-scope ids come back as
    ``None`` so routes answer 404 without leaking existence.
    """
    stmt = select(Icon).where(Icon.id == icon_id)
    if user_id is None:
        stmt = stmt.where(Icon.is_global.is_(True))
    else:
        stmt = stmt.where(Icon.owner_user_id == user_id)
    return db.execute(stmt).scalars().first()


def _name_taken(db: Session, name: str, *, user_id: int | None, exclude_id: int | None = None) -> bool:
    # ``.first()`` (not ``scalar_one_or_none``) mirrors the teams-service
    # posture: no DB uniqueness, so a concurrent double-insert must not
    # turn later lookups into MultipleResultsFound 500s.
    stmt = select(Icon.id).where(func.lower(Icon.name) == name.lower())
    if user_id is None:
        stmt = stmt.where(Icon.is_global.is_(True))
    else:
        stmt = stmt.where(Icon.owner_user_id == user_id)
    if exclude_id is not None:
        stmt = stmt.where(Icon.id != exclude_id)
    return db.execute(stmt).scalars().first() is not None


def dedupe_name(db: Session, name: str, *, user_id: int | None) -> str:
    """Return *name*, suffixed ``" (2)"``, ``" (3)"`` … until free in scope.

    The base is truncated so the suffixed candidate never exceeds the
    column's 120 characters — team names (the batch-import source) may
    already sit at the limit, and Postgres would refuse the overflow.
    """
    if not _name_taken(db, name, user_id=user_id):
        return name
    for n in range(2, 100):
        suffix = f" ({n})"
        candidate = f"{name[: _MAX_NAME_LEN - len(suffix)]}{suffix}"
        if not _name_taken(db, candidate, user_id=user_id):
            return candidate
    raise IconError(f"Could not find a free name for {name!r}.")


# ---- mutations ---------------------------------------------------------------


def create_icon(
    db: Session,
    *,
    name: str,
    raw: bytes,
    user_id: int | None,
    dedupe: bool = False,
) -> Icon:
    """Process *raw* and persist a new icon in the given scope.

    ``user_id=None`` creates a global icon (admin); otherwise personal,
    with the per-user quota enforced. ``dedupe=True`` auto-suffixes a
    taken name (batch import); otherwise a duplicate raises.

    The file is written before the row; the caller's surrounding
    commit failing triggers a best-effort unlink via the exception
    path here.
    """
    name = (name or "").strip()
    if not name:
        raise IconError("Icon name is required.")
    if len(name) > _MAX_NAME_LEN:
        raise IconError(f"Icon name is too long (max {_MAX_NAME_LEN} characters).")
    if user_id is not None and user_icon_count(db, user_id) >= ICONS_MAX_PER_USER:
        raise IconError(f"Icon quota reached ({ICONS_MAX_PER_USER}).")
    if dedupe:
        name = dedupe_name(db, name, user_id=user_id)
    elif _name_taken(db, name, user_id=user_id):
        raise IconError(f"An icon named {name!r} already exists.")

    processed = process_icon_upload(raw)
    filename = _store_file(processed.content)
    icon = Icon(
        name=name,
        filename=filename,
        mime="image/webp",
        width=processed.width,
        height=processed.height,
        size_bytes=len(processed.content),
        is_global=user_id is None,
        owner_user_id=user_id,
    )
    db.add(icon)
    try:
        db.flush()
    except BaseException:
        _unlink_file(filename)
        raise
    return icon


def rename_icon(db: Session, icon: Icon, name: str) -> Icon:
    name = (name or "").strip()
    if not name:
        raise IconError("Icon name is required.")
    if len(name) > _MAX_NAME_LEN:
        raise IconError(f"Icon name is too long (max {_MAX_NAME_LEN} characters).")
    scope_user = None if icon.is_global else icon.owner_user_id
    if _name_taken(db, name, user_id=scope_user, exclude_id=icon.id):
        raise IconError(f"An icon named {name!r} already exists.")
    icon.name = name
    return icon


def usage_count(db: Session, icon: Icon) -> int:
    """How many teams currently point at this icon's URL."""
    url = icon_public_url(icon.filename)
    return int(
        db.execute(
            select(func.count()).select_from(Team).where(Team.icon_url == url)
        ).scalar_one()
    )


def delete_icon(db: Session, icon: Icon) -> int:
    """Delete *icon*, clearing every team that referenced it.

    Returns the number of teams whose ``icon_url`` was cleared. The file
    is unlinked only once the caller's transaction actually commits — a
    rollback after this call restores the row AND keeps the file, so the
    two stores never disagree. If the session closes without committing,
    the listener simply never fires and the worst case is an orphaned
    file (inert), never a dangling row pointing at nothing.
    """
    url = icon_public_url(icon.filename)
    cleared = db.execute(
        update(Team).where(Team.icon_url == url).values(icon_url=None)
    ).rowcount or 0
    filename = icon.filename
    db.delete(icon)
    db.flush()
    event.listen(db, "after_commit", lambda session: _unlink_file(filename), once=True)
    return int(cleared)


def import_icons_from_teams(
    db: Session,
    teams: list[Team],
    *,
    user_id: int | None,
) -> list[dict]:
    """Convert each team's external logo URL into a hosted library icon.

    For every team: download the current ``icon_url`` (SSRF-guarded,
    size-capped), run it through the normal upload pipeline, create an
    icon named after the team (auto-suffixed on collision), and point
    the team at the hosted URL. Committed **per team**, so one failure
    never rolls back earlier conversions.

    Returns one result dict per team, in input order:
    ``{team_id, team_name, status: ok|skipped|error, icon_id?, icon_url?, error?}``.
    """
    results: list[dict] = []
    for team in teams:
        base = {"team_id": team.id, "team_name": team.name}
        source = (team.icon_url or "").strip()
        if not source:
            results.append({**base, "status": "skipped", "error": "no icon URL"})
            continue
        if source.startswith(ICONS_URL_PREFIX):
            # Already hosted — makes re-running the import idempotent.
            results.append({**base, "status": "skipped", "error": "already hosted"})
            continue
        if not source.lower().startswith(("http://", "https://")):
            results.append(
                {**base, "status": "skipped", "error": "not an external http(s) URL"}
            )
            continue
        try:
            raw = fetch_guarded(
                source,
                max_bytes=ICONS_MAX_UPLOAD_BYTES,
                timeout=ICONS_IMPORT_TIMEOUT_SECONDS,
            )
            icon = create_icon(
                db, name=team.name, raw=raw, user_id=user_id, dedupe=True,
            )
            url = icon_public_url(icon.filename)
            team.icon_url = url
            db.commit()
        except (GuardedFetchError, IconError) as exc:
            db.rollback()
            results.append({**base, "status": "error", "error": str(exc)})
            continue
        except Exception:
            # Per-team isolation is the contract: a commit that dies on a
            # transient DB error (lock timeout, disk) must not take the
            # whole batch down with a 500. Log the real cause; the client
            # gets a generic marker rather than internals.
            logger.exception("Icon import failed for team %s (%s)", team.id, team.name)
            db.rollback()
            results.append({**base, "status": "error", "error": "internal error"})
            continue
        results.append(
            {**base, "status": "ok", "icon_id": icon.id, "icon_url": url}
        )
    return results


def filenames_for_user(db: Session, user_id: int) -> list[str]:
    """Icon files owned by *user_id* — captured before a user delete.

    The rows vanish via FK cascade when the user row goes; the caller
    unlinks these files after the commit.
    """
    return list(
        db.execute(
            select(Icon.filename).where(Icon.owner_user_id == user_id)
        ).scalars().all()
    )


def unlink_files(filenames: list[str]) -> None:
    for filename in filenames:
        _unlink_file(filename)
