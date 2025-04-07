import re
import asyncio
import logging
import json
import os
from nicegui import ui
from app_storage import AppStorage
from authentication import PasswordAuthenticator
from backend import Backend
from messages import Messages

logger = logging.getLogger("OidDialog")


class OidDialog:

    hide_custom_overlay_input = False

    show_predefined_overlays = False
    overlays_json = os.environ.get('PREDEFINED_OVERLAYS', None)
    if overlays_json == None or overlays_json == '':
        predefined_overlays = None
    else: 
        show_predefined_overlays = True
        hide_custom_overlay_input = os.environ.get('HIDE_CUSTOM_OVERLAY_WHEN_PREDEFINED', 'false') == 'true' 
        predefined_overlays = json.loads(overlays_json)
    

    UNO_CONTROL_BASE_URL = 'https://app.overlays.uno/control/'
    UNO_OUTPUT_BASE_URL = 'https://app.overlays.uno/output/'
    CONTROL_TOKEN_KEY = 'control_token'
    OUTPUT_URL_KEY = 'output_url'


    def __init__(self, backend: Backend):
        self.dialog = ui.dialog().props('persistent')
        self.control_url_input = None
        #self.output_url_input = None
        self.result = None
        self.backend = backend
        self.checkBoxEnabled = False
        with self.dialog, ui.card().classes('w-[400px] !max-w-full'):
            self.radioButton = None
            current_user = AppStorage.load(AppStorage.Category.USERNAME, None)
            with ui.row().classes('w-full'):
                if OidDialog.hide_custom_overlay_input == False:
                    self.control_url_input = ui.input(label=Messages.get(Messages.CONTROL_URL), placeholder=OidDialog.UNO_CONTROL_BASE_URL+'<Control Token>').classes('w-full')
                if OidDialog.show_predefined_overlays:
                    self.checkBoxEnabled = True
                    result = []
                    for k,v in OidDialog.predefined_overlays.items():
                        allowed_users = v.get('allowed_users', None)
                        if allowed_users == None or current_user in allowed_users:
                            result.append(k)
                    if OidDialog.hide_custom_overlay_input == False:
                        self.radioButton = ui.checkbox(Messages.get(Messages.USE_PREDEFINED_OVERLAYS)).on_value_change(self.update_selector)
                    else:
                        self.checkBoxEnabled = False
                    self.predefined_overlay_selector = ui.select(result, value=result[0]).classes('w-full w-[300px]')
                    if self.checkBoxEnabled:
                        self.update_selector()
            with ui.row().classes('w-full'):
                if current_user != None:
                    ui.button(Messages.get(Messages.LOGOUT), on_click=PasswordAuthenticator.logout)    
                ui.space()
                self.submit_button = ui.button("OK", on_click=self.submit)

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
        #logger.debug('User submitted output: '+self.output_url_input.value)
        self.submit_button.props(add='loading')
        await asyncio.sleep(0.5)
        output = None
        if  (OidDialog.show_predefined_overlays and self.checkBoxEnabled == False)  or (self.radioButton != None and self.radioButton.value):
            token = OidDialog.predefined_overlays[self.predefined_overlay_selector.value]['control']
            output = OidDialog.predefined_overlays[self.predefined_overlay_selector.value].get('output', None)
        else:
            token = self.extract_oid(self.control_url_input.value)
            logger.debug("Extracted %s", token)
        if OidDialog.process_validation(self.backend.validate_and_store_model_for_oid(token)):
            self.result = {
                OidDialog.CONTROL_TOKEN_KEY: token
            }
            logger.debug("Valid")

            if output != None:
                self.result[OidDialog.OUTPUT_URL_KEY] = self.compose_output(output)
            self.dialog.submit(self.result)
        else:
            self.submit_button.props(remove='loading')
                

    def process_validation(validationResult, show_warning=True):
            if validationResult == Backend.ValidationResult.VALID:
                return True
            if show_warning:
                if validationResult == Backend.ValidationResult.DEPRECATED:
                    ui.notify(Messages.get(Messages.OVERLAY_DEPRECATED), color='negative')
                elif validationResult == Backend.ValidationResult.INVALID:
                    ui.notify(Messages.get(Messages.INVALID_OVERLAY_CONTROL_TOKEN), color='negative')
                elif validationResult == Backend.ValidationResult.EMPTY:
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
    

