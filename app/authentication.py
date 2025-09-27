import os
import logging
import asyncio
import json
from nicegui import app, ui
from fastapi import Request
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.messages import Messages
from app.app_storage import AppStorage
from app.env_vars_manager import EnvVarsManager

logger = logging.getLogger("Authenticator")

unrestricted_page_routes = {'/login'}

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Allow all NiceGUI specific routes to pass through without authentication
        if request.url.path.startswith('/_nicegui'):
            return await call_next(request)
        
        # If the user is not authenticated and the requested page is not the login page
        if not AppStorage.load(AppStorage.Category.AUTHENTICATED, False) and request.url.path not in unrestricted_page_routes:
            # Store the path the user wanted to access using the AppStorage abstraction
            AppStorage.save(AppStorage.Category.REDIRECT_PATH, request.url.path)
            # Redirect to the login page
            return RedirectResponse('/login')

        # If the user is authenticated, proceed to the requested page
        return await call_next(request)

class PasswordAuthenticator:
    UNO_OUTPUT_BASE_URL = 'https://app.overlays.uno/output/'
    
    def do_authenticate_users() -> bool:
        passwords_json = EnvVarsManager.get_env_var('SCOREBOARD_USERS', None)
        return passwords_json is not None and passwords_json.strip() != ''

    def check_user(user:str, password:str) -> bool:
        logger.debug("checking user")
        passwords_json = EnvVarsManager.get_env_var('SCOREBOARD_USERS', None)
        if not passwords_json or not passwords_json.strip():
            return False

        users = json.loads(passwords_json)
        userconf = users.get(user, None)
        if userconf != None:
            configuredPassword = userconf.get("password", None)
            logger.info("User '%s' found, checking password", user)
            if password == configuredPassword:
                logger.info("User '%s' authenticated, searching config", user)
                AppStorage.save(AppStorage.Category.USERNAME, user)
                AppStorage.save(AppStorage.Category.AUTHENTICATED, True)
                control = userconf.get("control", None)
                output = userconf.get("output", None)
                if control != None:
                    logger.info("Control data saved for user '%s'", user)
                    AppStorage.save(AppStorage.Category.CONFIGURED_OID, control)
                if output != None:
                    logger.info("Saving output for user '%s'", user)
                    AppStorage.save(AppStorage.Category.CONFIGURED_OUTPUT, PasswordAuthenticator.compose_output(output))
                return True
        logger.info("User '%s' not authenticated", user)
        return False

    def __init__(self, redirect_to:str):
        logger.debug("Initializing")
        self.dialog = ui.dialog().props('persistent')
        self.redirect_to = redirect_to 
        with self.dialog, ui.card().classes('w-[400px] !max-w-full'):
            self.username = ui.input(Messages.get(Messages.USERNAME)).classes('w-full')
            self.password = ui.input(Messages.get(Messages.PASSWORD), password=True, password_toggle_button=True).on('keydown.enter', self.try_login).classes('w-full')
            with ui.row().classes('w-full'):
                ui.space()
                ui.button(Messages.get(Messages.LOGIN), on_click=self.try_login)

    async def open(self):
        logger.debug("open dialog")
        await asyncio.sleep(0.5)
        return await self.dialog
    

    def try_login(self) -> None: 
            logger.debug("try login")
            if PasswordAuthenticator.check_user(self.username.value, self.password.value):
                AppStorage.save(AppStorage.Category.AUTHENTICATED, True)
                AppStorage.save(AppStorage.Category.USERNAME, self.username.value)
                self.dialog.submit(True)
            else:
                ui.notify(Messages.get(Messages.WRONG_USER_NAME), color='negative')
    
    def compose_output(output : str) -> str:
        prefix = PasswordAuthenticator.UNO_OUTPUT_BASE_URL
        if not output.startswith(prefix):
            return prefix + output
        return output

    def logout():
        logger.info("logging out")
        AppStorage.clear_user_storage()
        ui.navigate.to('./')