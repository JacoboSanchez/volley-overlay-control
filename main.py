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

from app.bootstrap import create_app
from app.env_vars_manager import EnvVarsManager
from app.logging_config import get_uvicorn_log_config, setup_logging

setup_logging()

app = create_app()


if __name__ == "__main__":
    import uvicorn

    port = EnvVarsManager.get_int_env("APP_PORT", 8080, minimum=1, maximum=65535)
    reload = EnvVarsManager.get_bool_env("APP_RELOAD")

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=reload,
        log_config=get_uvicorn_log_config(),
    )
