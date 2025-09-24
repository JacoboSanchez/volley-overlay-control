import re
import asyncio
import logging
import json
import os
from nicegui import ui
from app.app_storage import AppStorage
from app.authentication import PasswordAuthenticator
from app.backend import Backend
from app.state import State
from app.messages import Messages
from app.env_vars_manager import EnvVarsManager

logger = logging.getLogger("OidDialog")


class OidDialog:
    UNO_CONTROL_BASE_URL = 'https://app.overlays.uno/control/'
    UNO_OUTPUT_BASE_URL = 'https://app.overlays.uno/output/'
    CONTROL_TOKEN_KEY = 'control_token'
    OUTPUT_URL_KEY = 'output_url'


    def __init__(self, backend: Backend):
        
        logger.info("Initializing OidDialog")
        
        # --- CORRECTED LOGIC ---
        overlays_json = EnvVarsManager.get_env_var('PREDEFINED_OVERLAYS', None)
        if overlays_json and overlays_json.strip():
            self.predefined_overlays = json.loads(overlays_json)
            self.show_predefined_overlays = True
            logger.info("Loaded predefined overlays")
            self.hide_custom_overlay_input = EnvVarsManager.get_env_var('HIDE_CUSTOM_OVERLAY_WHEN_PREDEFINED', 'false') == 'true'
        else:
            self.predefined_overlays = None
            self.show_predefined_overlays = False
            self.hide_custom_overlay_input = False
            logger.info("No predefined overlays")
        # --- END OF CORRECTION ---

        self.dialog = ui.dialog().props('persistent')
        self.control_url_input = None
        self.result = None
        self.backend = backend
        self.checkBoxEnabled = False
        with self.dialog, ui.card().classes('w-[400px] !max-w-full'):
            self.radioButton = None
            current_user = AppStorage.load(AppStorage.Category.USERNAME, None)
            with ui.row().classes('w-full'):
                if self.hide_custom_overlay_input == False:
                    logger.debug("Initializing control url input")
                    self.control_url_input = ui.input(label=Messages.get(Messages.CONTROL_URL), placeholder=OidDialog.UNO_CONTROL_BASE_URL+'<Control Token>').classes('w-full').mark('control-url-input')
                if self.show_predefined_overlays:
                    self.checkBoxEnabled = True
                    result = []
                    for k,v in self.predefined_overlays.items():
                        allowed_users = v.get('allowed_users', None)
                        if allowed_users == None or current_user in allowed_users:
                            result.append(k)
                    if self.hide_custom_overlay_input == False:
                        self.radioButton = ui.checkbox(Messages.get(Messages.USE_PREDEFINED_OVERLAYS)).on_value_change(self.update_selector).mark('predefined-overlay-checkbox')
                    else:
                        self.checkBoxEnabled = False
                    logger.debug("Initializing predefined selector")
                    self.predefined_overlay_selector = ui.select(result, value=result[0]).classes('w-full w-[300px]').props('outlined').mark('predefined-overlay-selector')
                    if self.checkBoxEnabled:
                        self.update_selector()
            with ui.row().classes('w-full'):
                if current_user != None:
                    ui.button(Messages.get(Messages.LOGOUT), on_click=PasswordAuthenticator.logout).mark('logout-button-oid')
                ui.space()
                self.submit_button = ui.button("OK", on_click=self.submit).mark('submit-overlay-button')

    def update_selector(self):
        if self.checkBoxEnabled:
            if self.radioButton.value:
                if self.control_url_input != None:
                    self.control_url_input.set_enabled(False)
                if self.predefined_overlay_selector != None:
                    self.predefined_overlay_selector.set_enabled(True)
            else:
                if self.control_url_input != None: 
                    self.control_url_input.set_enabled(True)
                if self.predefined_overlay_selector != None:
                    self.predefined_overlay_selector.set_enabled(False)
            

    async def open(self):
        return await self.dialog

    def get_result(self):
        return self.result

    async def submit(self):
        logger.debug('User accepted config')
        self.submit_button.props(add='loading')
        await asyncio.sleep(0)
        output = None
        if  (self.show_predefined_overlays and self.checkBoxEnabled == False)  or (self.radioButton != None and self.radioButton.value):
            token = self.predefined_overlays[self.predefined_overlay_selector.value]['control']
            output = self.predefined_overlays[self.predefined_overlay_selector.value].get('output', None)
        else:
            token = self.extract_oid(self.control_url_input.value)
            logger.debug("Extracted %s", token)
        if OidDialog.process_validation(self.backend.validate_and_store_model_for_oid(token)):
            self.result = {
                self.CONTROL_TOKEN_KEY: token
            }
            logger.debug("Valid")

            if output != None:
                self.result[OidDialog.OUTPUT_URL_KEY] = self.compose_output(output)
            self.dialog.submit(self.result)
        else:
            logger.info("Not valid")
            self.submit_button.props(remove='loading')
                

    @staticmethod
    def process_validation(validationResult, show_warning=True):
            logger.debug("Validation result: %s", validationResult)
            if validationResult == State.OIDStatus.VALID:
                return True
            if show_warning:
                if validationResult == State.OIDStatus.DEPRECATED:
                    ui.notify(Messages.get(Messages.OVERLAY_DEPRECATED), color='negative')
                elif validationResult == State.OIDStatus.INVALID:
                    ui.notify(Messages.get(Messages.INVALID_OVERLAY_CONTROL_TOKEN), color='negative')
                elif validationResult == State.OIDStatus.EMPTY:
                    ui.notify(Messages.get(Messages.OVERLAY_CONFIGURATION_REQUIRED), color='negative')
            return False
    
    def extract_oid(self, url: str) -> str:
        pattern = r"^https://app\.overlays\.uno/control/([a-zA-Z0-9]*)\??"
        match = re.match(pattern, url)
        if match:
            return match.group(1)
        else:
            return url
        
    def compose_output(self, output : str) -> str:
        prefix = OidDialog.UNO_OUTPUT_BASE_URL
        if not output.startswith(prefix):
            return prefix + output
        return output