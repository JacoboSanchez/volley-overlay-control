"""GET /app-config — runtime configuration for the SPA."""

from fastapi import APIRouter

from app.app_config import get_app_title
from app.api.schemas import AppConfigResponse

router = APIRouter()


@router.get("/app-config", response_model=AppConfigResponse)
async def app_config() -> AppConfigResponse:
    """Return runtime app configuration consumed by the SPA on boot."""
    return AppConfigResponse(title=get_app_title())
