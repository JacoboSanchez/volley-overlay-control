import logging
import os
from app.logging_config import setup_logging
from app.authentication import PasswordAuthenticator, AuthMiddleware
from dotenv import load_dotenv
from app.startup import startup
from nicegui import ui, app
from app.env_vars_manager import EnvVarsManager

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
    custom_favicon='<svg xmlns="http://www.w3.org/2000/svg" enable-background="new 0 0 24 24" height="24px" viewBox="0 0 24 24" width="24px" fill="#5f6368"><g><rect fill="none" height="24" width="24"/></g><g><g><path d="M12,2C6.48,2,2,6.48,2,12c0,5.52,4.48,10,10,10s10-4.48,10-10C22,6.48,17.52,2,12,2z M13,4.07 c3.07,0.38,5.57,2.52,6.54,5.36L13,5.65V4.07z M8,5.08c1.18-0.69,3.33-1.06,3-1.02v7.35l-3,1.73V5.08z M4.63,15.1 C4.23,14.14,4,13.1,4,12c0-2.02,0.76-3.86,2-5.27v7.58L4.63,15.1z M5.64,16.83L12,13.15l3,1.73l-6.98,4.03 C7.09,18.38,6.28,17.68,5.64,16.83z M10.42,19.84 M12,20c-0.54,0-1.07-0.06-1.58-0.16l6.58-3.8l1.36,0.78 C16.9,18.75,14.6,20,12,20z M13,11.42V7.96l7,4.05c0,1.1-0.23,2.14-0.63,3.09L13,11.42z"/></g></g></svg>'
    reload = EnvVarsManager.get_env_var('APP_RELOAD', 'false').lower() in ("yes", "true", "t", "1")
    show = EnvVarsManager.get_env_var('APP_SHOW', 'false').lower() in ("yes", "true", "t", "1")
    ui.run(title=title, favicon=custom_favicon, on_air=onair, port=port, storage_secret=secret, show=show, reload=reload)