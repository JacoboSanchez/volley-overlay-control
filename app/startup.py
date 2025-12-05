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
from app.preview_page import PreviewPage


logger = logging.getLogger("Webapp")

# Serve fonts directory
app.add_static_files('/fonts', 'font')

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

    @ui.page('/preview')
    async def preview_page(x: float = None, y: float = None, width: float = None, height: float = None, output: str = None, control: str = None):
        if control:
            conf = Conf()
            backend = Backend(conf)
            
            if not output:
                output = backend.fetch_output_token(control)

            # If any geometry parameter is missing, try to fetch from backend customization
            if x is None or y is None or width is None or height is None:
                customization_data = backend.get_current_customization(customOid=control)
                if customization_data:
                    cust = Customization(customization_data)
                    if x is None: x = cust.get_h_pos()
                    if y is None: y = cust.get_v_pos()
                    if width is None: width = cust.get_width()
                    if height is None: height = cust.get_height()

        # Apply defaults if still missing
        x = x if x is not None else 0
        y = y if y is not None else 0
        width = width if width is not None else 100
        height = height if height is not None else 100

        if not output:
            ui.label("Output token is missing.")
            return
        
        url = OidDialog.UNO_OUTPUT_BASE_URL + output

        preview_page = PreviewPage(output=url, xpos=x, ypos=y, width=width, height=height)
        ui.on('resize', lambda e: preview_page.set_page_size(e.args['width'], e.args['height']))
        await preview_page.initialize()
        addHeader()
        await preview_page.create_page()

    async def run_page(custom_points_limit=None, custom_points_limit_last_set=None, custom_sets_limit=None, oid=None, output=None):
        logger.debug("run page")
        addHeader()
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
            if oid_to_use is None and oid is None and conf.single_overlay:
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

            if oid_to_use:
                # If we have an OID but missing the output token, try to fetch it automatically
                if not output_to_use:
                    token = backend.fetch_output_token(oid_to_use)
                    if token:
                        output_to_use = OidDialog.UNO_OUTPUT_BASE_URL + token

                logger.info("Using OID from %s: %s", source, oid_to_use)
                conf.oid = oid_to_use
                conf.output = output_to_use
            else:
                notification.dismiss()
                ui.label("Scoreboard could not be loaded. A valid overlay is required.").classes('m-auto text-negative')
                return

            scoreboard_page = GUI(tabs, conf, backend)
            customization_page = CustomizationPage(tabs, conf, backend, scoreboard_page, options_dialog)

            options_dialog.set_callback(scoreboard_page.update_button_style)

            with ui.tab_panels(tabs, value=scoreboardTab).classes("w-full h-full") as panels:
                scoreboardTabPanel = ui.tab_panel(scoreboardTab)
                with scoreboardTabPanel:
                    await scoreboard_page.init(custom_points_limit=custom_points_limit, custom_points_limit_last_set=custom_points_limit_last_set, custom_sets_limit=custom_sets_limit)
                configurationTabPanel = ui.tab_panel(configurationTab)
                with configurationTabPanel:
                    customization_page.init(configurationTabPanel)

            async def handle_resize(e):
                width = e.args['width']
                height = e.args['height']
                await scoreboard_page.set_page_size(width, height)
                logger.debug("New size: %s x %s", width, height)
                natural_width = 650 
                if not GUI.is_portrait(width, height) and width < natural_width:
                    scale = width / natural_width
                    logger.debug("scale size: %s", scale)
                    scoreboard_page.current_panel_style = f'transform: scale({scale}); transform-origin: top left; width: {natural_width}px;'
                    panels.style(scoreboard_page.current_panel_style)
                else:
                    logger.debug(f'current_style: {scoreboard_page.current_panel_style}')
                    panels.style(remove=scoreboard_page.current_panel_style, add='transform: none;')
                    
            
            ui.on('resize', handle_resize)
            
            await scoreboard_page.set_page_size(await get_client_width(), await get_client_height())

            with tabs:
                scoreboardTab
                configurationTab
        finally:
            notification.dismiss()

async def get_client_height():
    h = await ui.run_javascript('window.innerHeight')
    logger.debug("get_client_height: %s", h)
    return h

async def get_client_width():
    w = await ui.run_javascript('window.innerWidth')
    logger.debug("get_client_width: %s", w)
    return w

def addHeader():
    # Iterate through fonts in the directory
    font_css = ""
    font_dir = 'font'
    if os.path.exists(font_dir):
        for file in os.listdir(font_dir):
            if file.lower().endswith(('.ttf', '.otf', '.woff', '.woff2')):
                family_name = os.path.splitext(file)[0]
                font_css += f"""
                @font-face {{
                    font-family: '{family_name}';
                    src: url('/fonts/{file}');
                }}
                """
    
    # We must escape the brackets for the Javascript function because we are inside an f-string
    ui.add_head_html(f'''
    <style>
        {font_css}
    </style>
    <script>
    function emitSize() {{
        window.emitEvent('resize', {{
            width: document.body.offsetWidth,
            height: document.body.offsetHeight,
        }});
        }}
        window.onload = emitSize;
        window.onresize = emitSize;
    </script>
''')