import requests
import copy
import threading
import logging
from state import State
from app_storage import AppStorage


class Backend:
    logger = logging.getLogger("Backend")

    def __init__(self, config):
        self.conf = config
    
    def saveModel(self, current_model, simple):
        Backend.logger.info('saving model...')
        AppStorage.save(AppStorage.Category.CURRENT_MODEL, current_model, oid=self.conf.oid)
        to_save = copy.copy(current_model)
        if (simple):
            to_save = State.simplifyModel(to_save)
        if self.conf.multithread:
            threading.Thread(target=self.saveJSONState, args=(to_save,)).start()
        else:
            self.saveJSONState(to_save)
        Backend.logger.info('saved')
        
    def reduceGamesToOne(self):
        self.saveJSONState({State.T1SET5_INT:'0', State.T2SET5_INT:'0'})
        self.saveJSONState({State.T1SET4_INT:'0', State.T2SET4_INT:'0'})
        self.saveJSONState({State.T1SET3_INT:'0', State.T2SET3_INT:'0'})
        self.saveJSONState({State.T1SET2_INT:'0', State.T2SET2_INT:'0'})
    

    def saveJSONState(self, to_save):
        Backend.logger.info('saving JSON state...')
        return self.sendCommandWithIdAndContent("SetOverlayContent", to_save)
        
    def saveJSONCustomization(self, to_save):
        Backend.logger.info('saving JSON customization...')
        return self.sendCommandWithValue("SetCustomization", to_save)
    
    def changeOverlayVisibility(self, show):
        Backend.logger.info('changing overlay visibility, show: %s', show)
        command = "HideOverlay"
        if show:
            command = "ShowOverlay"
        return self.sendCommandWithIdAndContent(command)

    def sendCommandWithValue(self, command, value="", customOid=None):
        oid = customOid
        if customOid == None:
            oid = self.conf.oid
        jsonin = {"command": command, "value":value}
        logging.debug("Sending [%s]", jsonin)
        return Backend.process_response(requests.put(f'https://app.overlays.uno/apiv2/controlapps/{oid}/api', json=jsonin))

    def sendCommandWithIdAndContent(self, command, content="", customOid=None):
        oid = customOid
        if customOid == None:
            oid = self.conf.oid
        jsonin = {"command": command,  "id": self.conf.id, "content":content}
        logging.debug("Sending [%s]", jsonin)
        return Backend.process_response(requests.put(f'https://app.overlays.uno/apiv2/controlapps/{oid}/api', json=jsonin))


    def getCurrentStateModel(self, customOid=None, saveResult=False):
        oid = customOid
        if customOid == None:
            oid = self.conf.oid
        Backend.logger.info('getting state for oid %s', oid)
        currentModel = AppStorage.load(AppStorage.Category.CURRENT_MODEL, oid=oid)
        if currentModel != None:
            logging.info('Using stored model')
            logging.debug(currentModel)
            return currentModel
        response = self.sendCommandWithIdAndContent("GetOverlayContent", customOid=oid)
        if 200 == response.status_code:
            result = response.json()['payload']
            if saveResult == True:
                AppStorage.save(AppStorage.Category.CURRENT_MODEL, result, oid=oid)
            return result
        return None
    
    def getCurrentCustomizationStateModel(self):
        Backend.logger.info('getting customization')
        response = self.sendCommandWithIdAndContent("GetCustomization")
        if 200 == response.status_code:
            return response.json()['payload']
        return None

    def isVisible(self):
        response = self.sendCommandWithIdAndContent("GetOverlayVisibility")
        if 200 == response.status_code:
            return response.json()['payload']
        else:
            return False;

    def reset(self, state):
        self.saveModel(state.getResetModel(), False)
    
    def save(self, state, simple):
        self.saveModel(state.getCurrentModel(), simple)

    def process_response(response):
        if  response.status_code >= 300 :
            Backend.logger.warning("response %s: '%s'", response.status_code, response.text)
        else:
            Backend.logger.info("response status: %s", response.status_code)
            Backend.logger.debug("response message: '%s'", response.text)
        return response


    def validateAndStoreStateForOid(self, oid: str):
        if oid is None or oid.strip() == "":
            return False
        result = self.getCurrentStateModel(customOid=oid, saveResult=True)
        return result != None
    