"""Portable import/export for the admin-managed global team catalog."""

from __future__ import annotations

import base64
import binascii
import hashlib
import os
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import icons_service, teams_service
from app.api.schemas import (
    TeamCatalogConflictOut,
    TeamCatalogConflictResolution,
    TeamCatalogPreviewOut,
    TeamCatalogTransferImportOut,
    TeamCatalogTransferLogo,
    TeamCatalogTransferPackage,
    TeamCatalogTransferTeam,
)
from app.constants import ICONS_MAX_UPLOAD_BYTES, REQUEST_MAX_BODY_BYTES
from app.db.models.icon import Icon
from app.db.models.team import Team
from app.service_errors import ServiceError


class TeamCatalogTransferError(ServiceError):
    """The transfer package or one of its resolutions is invalid."""


class TeamCatalogTransferConflict(TeamCatalogTransferError):
    """The catalog changed or one or more conflicts remain unresolved."""

    status_code = 409


@dataclass(frozen=True)
class _PlannedTeam:
    incoming: TeamCatalogTransferTeam
    name: str
    existing: Team | None


_MAX_EMBEDDED_LOGO_BYTES = 5 * 1024 * 1024
_REQUEST_ENVELOPE_BYTES = max(
    1, min(1024 * 1024, REQUEST_MAX_BODY_BYTES // 4),
)
_MAX_TRANSFER_JSON_BYTES = max(
    1,
    min(6 * 1024 * 1024, REQUEST_MAX_BODY_BYTES - _REQUEST_ENVELOPE_BYTES),
)


def _validate_package_size(catalog: TeamCatalogTransferPackage) -> None:
    if len(catalog.model_dump_json().encode("utf-8")) > _MAX_TRANSFER_JSON_BYTES:
        raise TeamCatalogTransferError(
            "The catalog file is too large to import; export it without logos."
        )


def export_catalog(db: Session, *, include_logos: bool) -> TeamCatalogTransferPackage:
    """Build a versioned catalog package, optionally embedding hosted logos."""
    teams = teams_service.list_global(db)
    icons_by_url: dict[str, Icon] = {}
    if include_logos:
        icons_by_url = {
            icons_service.icon_public_url(icon.filename): icon
            for icon in db.execute(
                select(Icon).where(Icon.is_global.is_(True))
            ).scalars()
        }

    logos: dict[str, TeamCatalogTransferLogo] = {}
    embedded_bytes = 0
    rows: list[TeamCatalogTransferTeam] = []
    for index, team in enumerate(teams, start=1):
        logo_asset: str | None = None
        icon = icons_by_url.get(team.icon_url or "")
        if (
            include_logos
            and (team.icon_url or "").startswith(icons_service.ICONS_URL_PREFIX)
            and icon is None
        ):
            raise TeamCatalogTransferError(
                f"The hosted logo for {team.name!r} is not in the global icon library."
            )
        if icon is not None and os.path.basename(icon.filename) != icon.filename:
            raise TeamCatalogTransferError(
                f"The hosted logo for {team.name!r} has invalid metadata."
            )
        if icon is not None:
            try:
                path = os.path.join(icons_service.icons_dir(), icon.filename)
                with open(path, "rb") as stored:
                    raw = stored.read(ICONS_MAX_UPLOAD_BYTES + 1)
            except OSError as exc:
                raise TeamCatalogTransferError(
                    f"The hosted logo for {team.name!r} could not be read."
                ) from exc
            if not raw or len(raw) > ICONS_MAX_UPLOAD_BYTES:
                raise TeamCatalogTransferError(
                    f"The hosted logo for {team.name!r} is invalid."
                )
            logo_asset = hashlib.sha256(raw).hexdigest()[:32]
            if logo_asset not in logos:
                embedded_bytes += len(raw)
                if embedded_bytes > _MAX_EMBEDDED_LOGO_BYTES:
                    raise TeamCatalogTransferError(
                        "The hosted logos are too large for one catalog file; "
                        "export without logos."
                    )
                logos[logo_asset] = TeamCatalogTransferLogo(
                    data=base64.b64encode(raw).decode("ascii"),
                )
        rows.append(
            TeamCatalogTransferTeam(
                key=f"team-{index}",
                name=team.name,
                icon=team.icon_url,
                color=team.color,
                text_color=team.text_color,
                logo_asset=logo_asset,
            )
        )
    catalog = TeamCatalogTransferPackage(
        format="volley-overlay-team-catalog",
        version=1,
        teams=rows,
        logos=logos,
    )
    _validate_package_size(catalog)
    return catalog


def preview_import(
    db: Session, catalog: TeamCatalogTransferPackage,
) -> TeamCatalogPreviewOut:
    """Return catalog and in-file name collisions in package order."""
    _validate_package_size(catalog)
    existing_by_name: dict[str, Team] = {}
    for team in teams_service.list_global(db):
        existing_by_name.setdefault(team.name, team)

    first_in_file: dict[str, TeamCatalogTransferTeam] = {}
    conflicts: list[TeamCatalogConflictOut] = []
    for incoming in catalog.teams:
        name = incoming.name.strip()
        if not name:
            raise TeamCatalogTransferError("Team name is required.")
        first = first_in_file.get(name)
        if first is not None:
            conflicts.append(
                TeamCatalogConflictOut(
                    key=incoming.key,
                    incoming_name=name,
                    existing_name=first.name,
                    kind="file",
                )
            )
            continue
        first_in_file[name] = incoming
        existing = existing_by_name.get(name)
        if existing is not None:
            conflicts.append(
                TeamCatalogConflictOut(
                    key=incoming.key,
                    incoming_name=name,
                    existing_team_id=existing.id,
                    existing_name=existing.name,
                    kind="catalog",
                )
            )
    return TeamCatalogPreviewOut(teams=len(catalog.teams), conflicts=conflicts)


def _decode_logos(catalog: TeamCatalogTransferPackage) -> dict[str, bytes]:
    decoded: dict[str, bytes] = {}
    total_bytes = 0
    referenced = {team.logo_asset for team in catalog.teams if team.logo_asset}
    for key in referenced:
        asset = catalog.logos[key]
        try:
            raw = base64.b64decode(asset.data, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise TeamCatalogTransferError("A logo asset is not valid base64.") from exc
        if not raw or len(raw) > ICONS_MAX_UPLOAD_BYTES:
            raise TeamCatalogTransferError("A logo asset exceeds the image size limit.")
        total_bytes += len(raw)
        if total_bytes > _MAX_EMBEDDED_LOGO_BYTES:
            raise TeamCatalogTransferError(
                "The catalog's embedded logos exceed the total size limit."
            )
        # Validate every image before making the first database or file mutation.
        icons_service.process_icon_upload(raw)
        decoded[key] = raw
    return decoded


def _plan_import(
    db: Session,
    catalog: TeamCatalogTransferPackage,
    resolutions: list[TeamCatalogConflictResolution],
) -> list[_PlannedTeam]:
    preview = preview_import(db, catalog)
    conflicts = {conflict.key: conflict for conflict in preview.conflicts}
    decisions = {resolution.key: resolution for resolution in resolutions}
    unknown = set(decisions) - set(conflicts)
    if unknown:
        raise TeamCatalogTransferConflict("The catalog changed; preview the import again.")

    existing_by_id = {team.id: team for team in teams_service.list_global(db)}
    planned: list[_PlannedTeam] = []
    for incoming in catalog.teams:
        conflict = conflicts.get(incoming.key)
        decision = decisions.get(incoming.key)
        if conflict is None:
            planned.append(_PlannedTeam(incoming, incoming.name.strip(), None))
            continue
        if decision is None:
            raise TeamCatalogTransferConflict("The import has unresolved team conflicts.")
        if decision.action == "rename":
            planned.append(_PlannedTeam(incoming, (decision.name or "").strip(), None))
            continue
        if conflict.kind != "catalog" or conflict.existing_team_id is None:
            raise TeamCatalogTransferConflict(
                "Duplicate teams inside the file must be saved with another name."
            )
        existing = existing_by_id.get(conflict.existing_team_id)
        if (
            decision.expected_team_id != conflict.existing_team_id
            or existing is None
            or existing.name != conflict.existing_name
        ):
            raise TeamCatalogTransferConflict(
                "The catalog changed; preview the import again."
            )
        planned.append(_PlannedTeam(incoming, incoming.name.strip(), existing))

    destinations: dict[str, int | str] = {
        team.name: team.id for team in existing_by_id.values()
    }
    for item in planned:
        destination: int | str = item.existing.id if item.existing else item.incoming.key
        occupied = destinations.get(item.name)
        if occupied is not None and occupied != destination:
            raise TeamCatalogTransferConflict(
                f"A team named {item.name!r} would still conflict after import."
            )
        destinations[item.name] = destination
    return planned


def import_catalog(
    db: Session,
    catalog: TeamCatalogTransferPackage,
    resolutions: list[TeamCatalogConflictResolution],
) -> tuple[TeamCatalogTransferImportOut, list[str]]:
    """Apply a previewed package and return created icon files for rollback cleanup."""
    logo_bytes = _decode_logos(catalog)
    planned = _plan_import(db, catalog, resolutions)
    logo_urls: dict[str, str] = {}
    created_files: list[str] = []
    created = 0
    replaced = 0
    try:
        for item in planned:
            incoming = item.incoming
            icon_url = (incoming.icon or "").strip() or None
            if incoming.logo_asset:
                if incoming.logo_asset not in logo_urls:
                    icon = icons_service.create_icon(
                        db,
                        name=item.name,
                        raw=logo_bytes[incoming.logo_asset],
                        user_id=None,
                        dedupe=True,
                    )
                    created_files.append(icon.filename)
                    logo_urls[incoming.logo_asset] = icons_service.icon_public_url(
                        icon.filename
                    )
                icon_url = logo_urls[incoming.logo_asset]

            if item.existing is None:
                team = Team(
                    name=item.name,
                    icon_url=icon_url,
                    color=(incoming.color or "").strip() or None,
                    text_color=(incoming.text_color or "").strip() or None,
                    is_global=True,
                )
                db.add(team)
                created += 1
            else:
                item.existing.name = item.name
                item.existing.icon_url = icon_url
                item.existing.color = (incoming.color or "").strip() or None
                item.existing.text_color = (incoming.text_color or "").strip() or None
                replaced += 1
        db.flush()
    except BaseException:
        icons_service.unlink_files(created_files)
        raise
    return (
        TeamCatalogTransferImportOut(
            imported=len(planned), created=created, replaced=replaced,
        ),
        created_files,
    )
