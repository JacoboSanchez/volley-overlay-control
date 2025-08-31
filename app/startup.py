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
                # On successful login, set the authenticated flag and redirect client-side.
                app.storage.user.update({
                    AppStorage.Category.USERNAME: username.value,
                    AppStorage.Category.AUTHENTICATED: True
                })
                ui.navigate.to('/')
            else:
                ui.notify(Messages.get(Messages.WRONG_USER_NAME), color='negative')

        # The login form UI.
        with ui.card().classes('w-[400px] !max-w-full m-auto'):
            username = ui.input(Messages.get(Messages.USERNAME)).classes('w-full')
            password = ui.input(
                Messages.get(Messages.PASSWORD),
                password=True,
                password_toggle_button=True
            ).on('keydown.enter', do_login).classes('w-full')
            with ui.row().classes('w-full'):
                ui.space()
                ui.button(Messages.get(Messages.LOGIN), on_click=do_login)
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
        
        scoreboardTab = ui.tab(Customization.SCOREBOARD_TAB)
        configurationTab = ui.tab(Customization.CONFIG_TAB)

        tabs = ui.tabs().props('horizontal').classes("w-full")
        conf = Conf()
        options_dialog = OptionsDialog(conf)
        backend = Backend(conf)
        scoreboard_page = GUI(tabs, conf, backend)
        ui.on('resize', lambda e: scoreboard_page.set_page_size(e.args['width'], e.args['height']))
        await ui.context.client.connected()
        if custom_points_limit == None:
            custom_points_limit = conf.points
        if custom_points_limit_last_set == None:
            custom_points_limit_last_set = conf.points_last_set
        if custom_sets_limit == None:
            custom_sets_limit = conf.sets
        if oid != None:
            conf.oid = oid
            conf.output = None
        if output != None:
            conf.output = OidDialog.UNO_OUTPUT_BASE_URL+output

        storageOid = AppStorage.load(AppStorage.Category.CONFIGURED_OID, default=None)
        storageOutput = AppStorage.load(AppStorage.Category.CONFIGURED_OUTPUT, default=None)
        if oid == None and backend.validate_and_store_model_for_oid(storageOid) == Backend.ValidationResult.VALID:
            logger.info("Loading session oid: %s and output %s", storageOid, storageOutput)
            conf.oid = storageOid
            conf.output = storageOutput
        else:
            validationResult = backend.validate_and_store_model_for_oid(conf.oid)
            if validationResult != Backend.ValidationResult.VALID:
                notification.dismiss()
                logger.info("Current oid is not valid [%s]: %s", validationResult, conf.oid)
                dialog = OidDialog(backend=backend)
                result = await dialog.open()
                if result != None:
                    conf.oid = result[OidDialog.CONTROL_TOKEN_KEY]
                    outputCustom = result.get(OidDialog.OUTPUT_URL_KEY, None )
                    if outputCustom != None:
                        conf.output = outputCustom
                        AppStorage.save(AppStorage.Category.CONFIGURED_OUTPUT, conf.output)
                    logger.debug("Received oid %s", conf.oid)
                    AppStorage.save(AppStorage.Category.CONFIGURED_OID, conf.oid)

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
        notification.dismiss()

