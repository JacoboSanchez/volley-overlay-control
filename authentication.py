import os
import logging
import asyncio
import json
from nicegui import app, ui
from fastapi import Request
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from messages import Messages
from app_storage import AppStorage

logger = logging.getLogger("Authenticator")

do_authenticate = False
passwords_json = os.environ.get('SCOREBOARD_USERS', None)
if passwords_json == None or passwords_json == '':
    users = {}
else: 
    do_authenticate = True
    users = json.loads(passwords_json)

unrestricted_page_routes = {'/login'}

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not AppStorage.load(AppStorage.Category.AUTHENTICATED, False):
            if not request.url.path.startswith('/_nicegui') and request.url.path not in unrestricted_page_routes:
                return RedirectResponse(f'/login?redirect_to={request.url.path}')
        return await call_next(request)

class PasswordAuthenticator:
    UNO_OUTPUT_BASE_URL = 'https://app.overlays.uno/output/'
    
    def doAuthenticateUsers() -> bool:
        return do_authenticate

    def checkUser(user:str, password:str) -> bool:
        logger.debug("checking user")
        userconf = users.get(user, None)
        if userconf != None:
            configuredPassword = userconf.get("password", None)
            logger.info("User '%s' found, checking password", user)
            if password == configuredPassword:
                logger.info("User '%s' authenticated, searching config", user)
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
            if PasswordAuthenticator.checkUser(self.username.value, self.password.value):
                app.storage.user.update({AppStorage.Category.USERNAME: self.username.value, AppStorage.Category.AUTHENTICATED: True})
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
        AppStorage.clearUserStorage()
        ui.navigate.to('./')