import logging
import os
from app.logging_config import setup_logging
from app.authentication import PasswordAuthenticator, AuthMiddleware
from dotenv import load_dotenv
from app.startup import startup
from nicegui import ui, app
from app.env_vars_manager import EnvVarsManager
from app.constants import Constants

# Load environment variables only if tests are not running
if "PYTEST_CURRENT_TEST" not in os.environ:
    load_dotenv()

# Call the configuration function
setup_logging()
logger = logging.getLogger("Main")

if PasswordAuthenticator.do_authenticate_users():
    logger.info("User authentication enabled")
    app.add_middleware(AuthMiddleware)

# Use a custom attribute on the app object to ensure the startup handler
# is only registered once, even if the module is reloaded during tests.
if not getattr(app, 'startup_handler_registered', False):
    app.on_startup(startup)
    app.startup_handler_registered = True

if __name__ in {"__main__", "__mp_main__"}:
    onair = EnvVarsManager.get_env_var('UNO_OVERLAY_AIR_ID', None)
    if onair == '':
        onair = None
    port = int(EnvVarsManager.get_env_var('APP_PORT', 8080))
    title = EnvVarsManager.get_env_var('APP_TITLE', 'Scoreboard')
    secret = EnvVarsManager.get_env_var('STORAGE_SECRET', title+str(port))
    custom_favicon = Constants.CUSTOM_FAVICON
    reload = EnvVarsManager.get_env_var('APP_RELOAD', 'false').lower() in ("yes", "true", "t", "1")
    show = EnvVarsManager.get_env_var('APP_SHOW', 'false').lower() in ("yes", "true", "t", "1")
    ui.run(title=title, favicon=custom_favicon, on_air=onair, port=port, storage_secret=secret, show=show, reload=reload)