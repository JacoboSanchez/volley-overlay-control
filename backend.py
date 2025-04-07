import requests
import copy
import threading
import logging
from state import State
from app_storage import AppStorage
from enum import Enum

class Backend:
    logger = logging.getLogger("Backend")

    ValidationResult = Enum('ValidationResult', [('VALID', 'valid'), ('INVALID', 'invalid'), ('DEPRECATED', 'deprecated'), ('EMPTY', 'empty')])


    def __init__(self, config):
        self.conf = config
    
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
        self.save_json_model({State.T1SET5_INT:'0', State.T2SET5_INT:'0'})
        self.save_json_model({State.T1SET4_INT:'0', State.T2SET4_INT:'0'})
        self.save_json_model({State.T1SET3_INT:'0', State.T2SET3_INT:'0'})
        self.save_json_model({State.T1SET2_INT:'0', State.T2SET2_INT:'0'})
    

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
        oid = customOid
        if customOid == None:
            oid = self.conf.oid
        jsonin = {"command": command, "value":value}
        logging.debug("Sending [%s]", jsonin)
        return Backend.process_response(requests.put(f'https://app.overlays.uno/apiv2/controlapps/{oid}/api', json=jsonin))

    def send_command_with_id_and_content(self, command, content="", customOid=None):
        oid = customOid
        if customOid == None:
            oid = self.conf.oid
        jsonin = {"command": command,  "id": self.conf.id, "content":content}
        logging.debug("Sending [%s]", jsonin)
        return Backend.process_response(requests.put(f'https://app.overlays.uno/apiv2/controlapps/{oid}/api', json=jsonin))


    def get_current_model(self, customOid=None, saveResult=False):
        oid = customOid
        if customOid == None:
            oid = self.conf.oid
        Backend.logger.info('getting state for oid %s', oid)
        currentModel = AppStorage.load(AppStorage.Category.CURRENT_MODEL, oid=oid)
        if currentModel != None:
            logging.info('Using stored model')
            logging.debug(currentModel)
            return currentModel
        response = self.send_command_with_id_and_content("GetOverlayContent", customOid=oid)
        if 200 == response.status_code:
            result = response.json()['payload']
            if saveResult == True:
                AppStorage.save(AppStorage.Category.CURRENT_MODEL, result, oid=oid)
            return result
        return None
    
    def get_current_customization(self):
        Backend.logger.info('getting customization')
        response = self.send_command_with_id_and_content("GetCustomization")
        if 200 == response.status_code:
            return response.json()['payload']
        return None

    def is_visible(self):
        response = self.send_command_with_id_and_content("GetOverlayVisibility")
        if 200 == response.status_code:
            return response.json()['payload']
        else:
            return False;

    def reset(self, state):
        self.save_model(state.get_reset_model(), False)
    
    def save(self, state, simple):
        self.save_model(state.get_current_model(), simple)

    def process_response(response):
        if  response.status_code >= 300 :
            Backend.logger.warning("response %s: '%s'", response.status_code, response.text)
        else:
            Backend.logger.info("response status: %s", response.status_code)
            Backend.logger.debug("response message: '%s'", response.text)
        return response


    def validate_and_store_model_for_oid(self, oid: str):
        if oid is None or oid.strip() == "":
            return Backend.ValidationResult.EMPTY
        result = self.get_current_model(customOid=oid, saveResult=True)
        if result != None:
            if (result.get("game1State", None) != None):
                return Backend.ValidationResult.DEPRECATED
            return Backend.ValidationResult.VALID
        return Backend.ValidationResult.INVALID