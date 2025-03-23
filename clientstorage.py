import logging
from nicegui import app, ui
from state import State

class ClientStorage:
    CURRENT_MODEL = 'current_model'
    SIMPLE_MODE = 'simpleMode'
    DARK_MODE = 'darkMode'
    
    logger = logging.getLogger("Storage")


    def save(tag, value):
        ClientStorage.logger.debug('Saving %s to %s', value, tag)
        app.storage.tab[tag] = value

    def load(tag, default=None):
        result = app.storage.tab.get(tag, default)
        ClientStorage.logger.debug('Loaded %s: %s', tag, result)
        return result