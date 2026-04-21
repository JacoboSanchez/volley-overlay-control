"""Predefined data endpoints: /overlays, /teams, /themes, /links, /styles."""

import json
import logging
import urllib.parse

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import get_current_username, get_session, verify_api_key
from app.api.session_manager import GameSession
from app.authentication import PasswordAuthenticator
from app.customization import Customization
from app.env_vars_manager import EnvVarsManager
from app.oid_utils import compose_output, extract_oid

logger = logging.getLogger(__name__)

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
        if isinstance(config, dict)
        and (config.get('allowed_users') is None
             or (current_user and current_user in (config.get('allowed_users') or [])))
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

        # Build a preview-page URL pointing at the SPA /preview route. The
        # in-app preview card consumes the geometry params from this URL, and
        # users can also open it directly as a standalone scalable preview.
        # Custom overlays use layout_id=auto so the overlay JS reports its
        # render bounds via postMessage; geometry params are ignored in that
        # branch but kept for a uniform URL shape.
        if session.backend.is_custom_overlay(oid):
            layout_id = "auto"
            x = y = 0.0
            width = height = 100.0
        else:
            layout_id = session.conf.id or ""
            cust = session.customization
            x = cust.get_h_pos()
            y = cust.get_v_pos()
            width = cust.get_width()
            height = cust.get_height()

        base_url = str(request.base_url).rstrip('/')
        preview_qs = urllib.parse.urlencode({
            "output": overlay_url,
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "layout_id": layout_id,
        })
        links["preview"] = f"{base_url}/preview?{preview_qs}"

    return links


@router.get("/styles", dependencies=[Depends(verify_api_key)])
async def get_styles(session: GameSession = Depends(get_session)):
    """Return available overlay styles."""
    return await run_in_threadpool(session.backend.get_available_styles)
