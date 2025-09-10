import logging
import os
from app.oid_dialog import OidDialog
from app.gui import GUI
from app.options_dialog import OptionsDialog
from fastapi.responses import RedirectResponse
from app.authentication import AuthMiddleware, PasswordAuthenticator
from nicegui import ui, app
from app.customization import Customization
from app.customization_page import CustomizationPage
from app.conf import Conf
from app.backend import Backend
from app.app_storage import AppStorage
from app.messages import Messages
from fastapi import Request
from typing import Optional
from app.game_manager import GameManager
from app.state import State

logger = logging.getLogger("Webapp")


def startup() -> None:
    def reset_all():
        logger.info("Clearing storage")
        AppStorage.clear_user_storage()

    def process_parameters(logout=None):
        if logout == "true":
            reset_all()
            ui.navigate.to('./')

    @ui.page("/indoor")
    async def beach(control=None, output=None, logout=None):
        process_parameters(logout=logout)
        await run_page(custom_points_limit=25, custom_points_limit_last_set=15, custom_sets_limit=5, oid=control, output=output)

    @ui.page("/beach")
    async def beach(control=None, output=None, logout=None):
        process_parameters(logout=logout)
        await run_page(custom_points_limit=21, custom_points_limit_last_set=15, custom_sets_limit=3, oid=control, output=output)

    @ui.page("/")
    async def main(control=None, output=None, logout=None):
        logger.debug("root page")
        process_parameters(logout=logout)
        await run_page(oid=control, output=output)

    @ui.page('/login')
    async def login(request: Request) -> Optional[RedirectResponse]:
        # If the user is already authenticated, the middleware will handle redirection.
        # We just handle the login process itself.

        async def do_login():
            if PasswordAuthenticator.check_user(username.value, password.value):
                # On successful login, set the authenticated flag and username
                AppStorage.save(AppStorage.Category.USERNAME, username.value)
                AppStorage.save(AppStorage.Category.AUTHENTICATED, True)

                # Check for a redirect path, navigate there, then clear it.
                redirect_path = AppStorage.load(AppStorage.Category.REDIRECT_PATH, '/')
                AppStorage.save(AppStorage.Category.REDIRECT_PATH, None)
                ui.navigate.to(redirect_path)
            else:
                ui.notify(Messages.get(Messages.WRONG_USER_NAME), color='negative')

        # The login form UI.
        with ui.card().classes('w-[400px] !max-w-full m-auto'):
            username = ui.input(Messages.get(Messages.USERNAME)).classes('w-full').mark('username-input')
            password = ui.input(
                Messages.get(Messages.PASSWORD),
                password=True,
                password_toggle_button=True
            ).on('keydown.enter', do_login).classes('w-full').mark('password-input')
            with ui.row().classes('w-full'):
                ui.space()
                ui.button(Messages.get(Messages.LOGIN), on_click=do_login).mark('login-button')
        return None

    async def run_page(custom_points_limit=None, custom_points_limit_last_set=None, custom_sets_limit=None, oid=None, output=None):
        logger.debug("run page")
        # REMOVED: Authentication check was removed from here. It's now handled entirely by the middleware.
        
        ui.add_head_html('''
            <script>
            function emitSize() {
                window.emitEvent('resize', {
                    width: document.body.offsetWidth,
                    height: document.body.offsetHeight,
                });
                }
                window.onload = emitSize;
                window.onresize = emitSize;
            </script>
        ''')
        notification = ui.notification(Messages.get(Messages.LOADING), timeout=None, spinner=True)
        try:
            scoreboardTab = ui.tab(Customization.SCOREBOARD_TAB)
            configurationTab = ui.tab(Customization.CONFIG_TAB)

            tabs = ui.tabs().props('horizontal').classes("w-full")
            conf = Conf()
            if custom_points_limit is not None:
                conf.points = custom_points_limit
            if custom_points_limit_last_set is not None:
                conf.points_last_set = custom_points_limit_last_set
            if custom_sets_limit is not None:
                conf.sets = custom_sets_limit
            options_dialog = OptionsDialog(conf)
            backend = Backend(conf)
            await ui.context.client.connected()
            if custom_points_limit == None:
                custom_points_limit = conf.points
            if custom_points_limit_last_set == None:
                custom_points_limit_last_set = conf.points_last_set
            if custom_sets_limit == None:
                custom_sets_limit = conf.sets
            oid_to_use = None
            output_to_use = None
            source = "none"

            # 1. Check for OID in URL parameters (highest priority)
            if oid is not None:
                if backend.validate_and_store_model_for_oid(oid) == State.OIDStatus.VALID:
                    oid_to_use = oid
                    source = "URL"
                    if output:
                        output_to_use = OidDialog.UNO_OUTPUT_BASE_URL + output
                else:
                    logger.warning("Invalid OID provided in URL: %s", oid)

            # 2. If no valid OID from URL, check AppStorage (second priority)
            if oid_to_use is None:
                storage_oid = AppStorage.load(AppStorage.Category.CONFIGURED_OID, default=None)
                if storage_oid and backend.validate_and_store_model_for_oid(storage_oid) == State.OIDStatus.VALID:
                    oid_to_use = storage_oid
                    output_to_use = AppStorage.load(AppStorage.Category.CONFIGURED_OUTPUT, default=None)
                    source = "storage"

            # 3. If still no OID, check environment variables (third priority)
            if oid_to_use is None and oid is None:
                env_oid = conf.oid
                if env_oid and backend.validate_and_store_model_for_oid(env_oid) == State.OIDStatus.VALID:
                    oid_to_use = env_oid
                    output_to_use = conf.output
                    source = "environment"

            # 4. If no valid OID was found from any source, open the dialog
            if oid_to_use is None:
                notification.dismiss()
                logger.info("No valid OID from URL, storage, or environment. Opening dialog.")
                dialog = OidDialog(backend=backend)
                result = await dialog.open()
                if result:
                    oid_to_use = result.get(OidDialog.CONTROL_TOKEN_KEY)
                    output_to_use = result.get(OidDialog.OUTPUT_URL_KEY)
                    source = "dialog"
                    AppStorage.save(AppStorage.Category.CONFIGURED_OID, oid_to_use)
                    AppStorage.save(AppStorage.Category.CONFIGURED_OUTPUT, output_to_use)

            # --- End of New Logic ---

            if oid_to_use:
                logger.info("Using OID from %s: %s", source, oid_to_use)
                conf.oid = oid_to_use
                conf.output = output_to_use
            else:
                notification.dismiss()
                ui.label("Scoreboard could not be loaded. A valid overlay is required.").classes('m-auto text-negative')
                return

            scoreboard_page = GUI(tabs, conf, backend)
            ui.on('resize', lambda e: scoreboard_page.set_page_size(e.args['width'], e.args['height']))

            customization_page = CustomizationPage(tabs, conf, backend, scoreboard_page, options_dialog)
            with ui.tab_panels(tabs, value=scoreboardTab).classes("w-full"):
                scoreboardTabPanel = ui.tab_panel(scoreboardTab)
                with scoreboardTabPanel:
                    scoreboard_page.init(custom_points_limit=custom_points_limit, custom_points_limit_last_set=custom_points_limit_last_set, custom_sets_limit=custom_sets_limit)
                configurationTabPanel = ui.tab_panel(configurationTab)
                with configurationTabPanel:
                    customization_page.init(configurationTabPanel)
            with tabs:
                scoreboardTab
                configurationTab
        finally:
            notification.dismiss()