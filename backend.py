import requests
import copy
import threading
from state import State

class Backend:
    def __init__(self, config):
        self.conf = config

    def saveModel(self, current_model, simple):
        if (self.conf.debug):
            print('Saving model start')
        to_save = copy.copy(current_model)
        if (simple):
            to_save = State.simplifyModel(to_save, self)
        if self.conf.multithread:
            threading.Thread(target=self.saveJSONState, args=(to_save,)).start()
        else:
            self.saveJSONState(to_save)
        if (self.conf.debug):
            print('Saving model end')
        
    def reduceGamesToOne(self):
        self.saveJSONState({State.T1SET5_INT:'0', State.T2SET5_INT:'0' })
        self.saveJSONState({State.T1SET4_INT:'0', State.T2SET4_INT:'0' })
        self.saveJSONState({State.T1SET3_INT:'0', State.T2SET3_INT:'0' })
        self.saveJSONState({State.T1SET2_INT:'0', State.T2SET2_INT:'0' })
    

    def saveJSONState(self, to_save):
        if (self.conf.debug):
            print('Saving JSON state')
        return self.sendCommandWithIdAndContent("SetOverlayContent", to_save)
    
    def saveJSONCustomization(self, to_save):
        return self.sendCommandWithValue("SetCustomization", to_save)
    
    def changeOverlayVisibility(self, show):
        command = "HideOverlay"
        if show:
            command = "ShowOverlay"
        return self.sendCommandWithIdAndContent(command)

    def sendCommandWithValue(self, command, value=""):
        jsonin = {"command": command, "value":value}
        return requests.put(f'https://app.overlays.uno/apiv2/controlapps/{self.conf.oid}/api', json=jsonin)

    def sendCommandWithIdAndContent(self, command, content=""):
        jsonin = {"command": command,  "id": self.conf.id, "content":content}
        return requests.put(f'https://app.overlays.uno/apiv2/controlapps/{self.conf.oid}/api', json=jsonin)

    def getCurrentStateModel(self):
        if (self.conf.debug):
            print('getCurrentState')
        response = self.sendCommandWithIdAndContent("GetOverlayContent")
        if 200 == response.status_code:
            if (self.conf.debug):
                print('getCurrentState success')
            return response.json()['payload']
        if (self.conf.debug):
            print('getCurrentState error')
        return None
    
    def getCurrentCustomizationStateModel(self):
        if (self.conf.debug):
            print('getCurrentCustomization')
        response = self.sendCommandWithIdAndContent("GetCustomization")
        if 200 == response.status_code:
            if (self.conf.debug):
                print('getCurrentCustomization success')
            return response.json()['payload']
        if (self.conf.debug):
            print('getCurrentCustomization error')
        return None

    def isVisible(self):
        response = self.sendCommandWithIdAndContent("GetOverlayVisibility")
        if 200 == response.status_code:
            return response.json()['payload']

    def reset(self, state):
        self.saveModel(state.getResetModel(), False)
    
    def save(self, state, simple):
        self.saveModel(state.getCurrentModel(), simple)

    def saveCustomization(self, customization):
        return self 

        