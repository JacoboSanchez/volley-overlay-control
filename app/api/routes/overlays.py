"""Predefined data endpoints: /overlays, /teams, /themes, /links, /styles."""

import json
import logging

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import get_current_username, get_session, verify_api_key
from app.api.session_manager import GameSession
from app.authentication import PasswordAuthenticator
from app.customization import Customization
from app.env_vars_manager import EnvVarsManager
from app.oid_utils import compose_output, extract_oid

logger = logging.getLogger("APIRoutes")

router = APIRouter()


class OverlayPayload(BaseModel):
    """Predefined overlay entry returned by ``GET /overlays``."""

    name: str = Field(..., description="Display name of the overlay")
    oid: str = Field(..., description="Overlay identifier")


@router.get(
    "/overlays",
    response_model=list[OverlayPayload],
    dependencies=[Depends(verify_api_key)],
)
async def get_overlays(authorization: str = Header(None)):
    """Return predefined overlays available for selection.

    Sourced exclusively from the ``PREDEFINED_OVERLAYS`` environment
    variable (also populated via the remote configurator). Entries are
    filtered by ``allowed_users`` using the caller's identity when user
    authentication is enabled.
    """
    overlays_json = EnvVarsManager.get_env_var('PREDEFINED_OVERLAYS', None)
    if not overlays_json or not overlays_json.strip():
        return []

    try:
        env_overlays = json.loads(overlays_json)
    except json.JSONDecodeError:
        logger.warning("PREDEFINED_OVERLAYS contains invalid JSON")
        return []

    if not isinstance(env_overlays, dict):
        logger.warning("PREDEFINED_OVERLAYS is not a JSON object")
        return []

    current_user = None
    if PasswordAuthenticator.do_authenticate_users():
        current_user = get_current_username(authorization)

    return [
        {"name": name, "oid": extract_oid(config.get('control', ''))}
        for name, config in env_overlays.items()
        if config.get('allowed_users') is None
        or (current_user and current_user in config.get('allowed_users'))
    ]


@router.get("/teams", dependencies=[Depends(verify_api_key)])
async def get_teams():
    """Return predefined team names with icon/color data."""
    await run_in_threadpool(Customization.refresh)
    return Customization.predefined_teams


@router.get("/themes", dependencies=[Depends(verify_api_key)])
async def get_themes():
    """Return available theme definitions."""
    await run_in_threadpool(Customization.refresh)
    return Customization.THEMES


@router.get("/links", dependencies=[Depends(verify_api_key)])
async def get_links(request: Request,
                    session: GameSession = Depends(get_session)):
    """Return control, overlay, and preview links for the session."""
    oid = session.oid
    output = session.conf.output
    links = {}

    if not session.backend.is_custom_overlay(oid):
        links["control"] = f"https://app.overlays.uno/control/{oid}"

    if output and output.strip():
        overlay_url = (
            output if output.startswith("http")
            else compose_output(output)
        )
        links["overlay"] = overlay_url

        # Custom overlays need a preview URL for the frontend preview card.
        # The preview URL encodes geometry hints; the OverlayPreview component
        # uses postMessage bounds for actual positioning.
        if session.backend.is_custom_overlay(oid):
            links["preview"] = f"{overlay_url}?layout_id=auto"

    return links


@router.get("/styles", dependencies=[Depends(verify_api_key)])
async def get_styles(session: GameSession = Depends(get_session)):
    """Return available overlay styles."""
    return await run_in_threadpool(session.backend.get_available_styles)
