import re
from nicegui import ui
import logging
from backend import Backend

logger = logging.getLogger("OidDialog")


class OidDialog:

    UNO_CONTROL_BASE_URL = 'https://app.overlays.uno/control/'
    UNO_OUTPUT_BASE_URL = 'https://app.overlays.uno/output/'
    CONTROL_TOKEN_KEY = 'control_token'
    OUTPUT_URL_KEY = 'output_url'


    def __init__(self, backend: Backend):
        self.dialog = ui.dialog().props('persistent')
        self.control_url_input = None
        self.output_url_input = None
        self.result = None
        self.backend = backend

        with self.dialog, ui.card().classes('w-[400px] !max-w-full'):
            ui.label("Enter Control and Output URLs")
            self.control_url_input = ui.input(label="Control URL", placeholder=OidDialog.UNO_CONTROL_BASE_URL+'<Control Token>').classes('w-full')
            self.output_url_input = ui.input(label="Output URL", placeholder=OidDialog.UNO_OUTPUT_BASE_URL+'<Output Token>').classes('w-full')
            with ui.row():
                ui.button("OK", on_click=self.submit)

    async def open(self):
        return await self.dialog

    def get_result(self):
        return self.result

    def submit(self):
        logger.debug('User submitted control: '+self.control_url_input.value)
        logger.debug('User submitted output: '+self.output_url_input.value)
        token = self.extract_oid(self.control_url_input.value)
        if self.backend.validateAndStoreStateForOid(token):
            self.result = {
                OidDialog.CONTROL_TOKEN_KEY: token,
                OidDialog.OUTPUT_URL_KEY: self.compose_output(self.output_url_input.value),
            }
            self.dialog.submit(True)
        else:
            ui.notify('Invalid overlay control token received [' + token + ']')
    
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