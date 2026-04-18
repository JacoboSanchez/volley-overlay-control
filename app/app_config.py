"""Runtime app-level configuration exposed to the frontend.

Currently only the application title is configurable via the ``APP_TITLE``
environment variable. The value is consumed both by the FastAPI app
(injected into the served ``index.html`` and PWA manifest) and by the SPA
(via ``GET /api/v1/app-config``).
"""

from app.env_vars_manager import EnvVarsManager

DEFAULT_APP_TITLE = "Volley Scoreboard"


def get_app_title() -> str:
    """Return the configured application title, falling back to the default."""
    value = EnvVarsManager.get_env_var("APP_TITLE", DEFAULT_APP_TITLE)
    if isinstance(value, str):
        value = value.strip()
    return value or DEFAULT_APP_TITLE
