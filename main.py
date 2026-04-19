"""Entry point: load environment, set up logging, and build the FastAPI app.

This module intentionally stays tiny — all assembly logic lives in
:mod:`app.bootstrap` so the app can be built in tests without relying on
side-effects of importing ``main``.
"""

import os

from dotenv import load_dotenv

# Load environment variables only if tests are not running
if "PYTEST_CURRENT_TEST" not in os.environ:
    load_dotenv()

from app.logging_config import get_uvicorn_log_config, setup_logging
from app.config_validator import validate_config
from app.env_vars_manager import EnvVarsManager
from app.bootstrap import create_app

validate_config()
setup_logging()

app = create_app()


if __name__ == "__main__":
    import uvicorn

    port = int(EnvVarsManager.get_env_var("APP_PORT", 8080))
    reload = EnvVarsManager.get_env_var("APP_RELOAD", "false").lower() in (
        "yes", "true", "t", "1",
    )

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=reload,
        log_config=get_uvicorn_log_config(),
    )
