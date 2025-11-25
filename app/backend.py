import requests
import copy
import threading
import logging
import re
from app.state import State
from app.app_storage import AppStorage

class Backend:
    logger = logging.getLogger("Backend")


    def __init__(self, config):
        self.conf = config
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': self.conf.rest_user_agent,
            'Content-Type': 'application/json',
            'Accept': 'application/json, text/plain, */*'
        })

    def save_model(self, current_model, simple):
        Backend.logger.info('saving model...')
        AppStorage.save(AppStorage.Category.CURRENT_MODEL, current_model, oid=self.conf.oid)
        to_save = copy.copy(current_model)
        if (simple):
            to_save = State.simplify_model(to_save)
        if self.conf.multithread:
            threading.Thread(target=self.save_json_model, args=(to_save,)).start()
        else:
            self.save_json_model(to_save)
        Backend.logger.info('saved')

    def reduce_games_to_one(self):
        """
        Resets the scores of sets 2, 3, 4, and 5 to zero in a single API call.
        """
        scores_to_reset = {
            State.T1SET5_INT: '0', State.T2SET5_INT: '0',
            State.T1SET4_INT: '0', State.T2SET4_INT: '0',
            State.T1SET3_INT: '0', State.T2SET3_INT: '0',
            State.T1SET2_INT: '0', State.T2SET2_INT: '0'
        }
        self.save_json_model(scores_to_reset)

    def save_json_model(self, to_save):
        Backend.logger.info('saving JSON model...')
        return self.send_command_with_id_and_content("SetOverlayContent", to_save)

    def save_json_customization(self, to_save):
        Backend.logger.info('saving JSON customization...')
        return self.send_command_with_value("SetCustomization", to_save)

    def change_overlay_visibility(self, show):
        Backend.logger.info('changing overlay visibility, show: %s', show)
        command = "HideOverlay"
        if show:
            command = "ShowOverlay"
        return self.send_command_with_id_and_content(command)

    def send_command_with_value(self, command, value="", customOid=None):
        oid = customOid if customOid is not None else self.conf.oid
        jsonin = {"command": command, "value": value}
        return self.do_send_request(oid, jsonin)

    def send_command_with_id_and_content(self, command, content="", customOid=None):
        oid = customOid if customOid is not None else self.conf.oid
        jsonin = {"command": command,  "id": self.conf.id, "content": content}
        return self.do_send_request(oid, jsonin)

    def do_send_request(self, oid, jsonin):
        logging.debug("Sending [%s] via Session", jsonin)
        url = f'https://app.overlays.uno/apiv2/controlapps/{oid}/api'
        response = self.session.put(url, json=jsonin)
        return self.process_response(response)

    def get_current_model(self, customOid=None, saveResult=False):
        oid = customOid if customOid is not None else self.conf.oid
        Backend.logger.info('getting state for oid %s', oid)
        currentModel = AppStorage.load(AppStorage.Category.CURRENT_MODEL, oid=oid)
        if currentModel is not None:
            logging.info('Using stored model')
            logging.debug(currentModel)
            return currentModel
        response = self.send_command_with_id_and_content("GetOverlayContent", customOid=oid)
        if response.status_code == 200:
            result = response.json()['payload']
            if saveResult:
                AppStorage.save(AppStorage.Category.CURRENT_MODEL, result, oid=oid)
            return result
        return None

    def get_current_customization(self):
        Backend.logger.info('getting customization')
        response = self.send_command_with_id_and_content("GetCustomization")
        if response.status_code == 200:
            return response.json()['payload']
        return None

    def is_visible(self):
        response = self.send_command_with_id_and_content("GetOverlayVisibility")
        if response.status_code == 200:
            return response.json()['payload']
        else:
            return False

    def reset(self, state):
        self.save_model(state.get_reset_model(), False)

    def save(self, state, simple):
        self.save_model(state.get_current_model(), simple)

    def process_response(self, response):
        if response.status_code >= 300:
            logging.warning("response %s: '%s'", response.status_code, response.text)
        else:
            logging.info("response status: %s", response.status_code)
            logging.debug("response message: '%s'", response.text)
        return response

    def validate_and_store_model_for_oid(self, oid: str):
        if oid is None or oid.strip() == "":
            logging.debug("empty oid: %s", oid)
            return State.OIDStatus.EMPTY
        result = self.get_current_model(customOid=oid, saveResult=True)
        if result is not None:
            if result.get("game1State") is not None:
                return State.OIDStatus.DEPRECATED
            return State.OIDStatus.VALID
        return State.OIDStatus.INVALID
    
    def fetch_output_token(self, oid):
        """
        Fetches the output token associated with the given OID by querying the overlays.uno API.
        """
        try:
            Backend.logger.info(f"Fetching output token for OID: {oid}")
            url = f'https://app.overlays.uno/apiv2/controlapps/{oid}'
            response = self.session.get(url)
            if response.status_code == 200:
                data = response.json()
                output_url = data.get('outputUrl')
                if output_url:
                    # Expecting format: .../output/<token>/...
                    match = re.search(r'/output/([^/?]+)', output_url)
                    if match:
                        token = match.group(1)
                        Backend.logger.info(f"Output token found: {token}")
                        return token
            else:
                Backend.logger.warning(f"Failed to fetch output token for OID {oid}: {response.status_code}")
        except Exception as e:
            Backend.logger.error(f"Error fetching output token: {e}")
        return None