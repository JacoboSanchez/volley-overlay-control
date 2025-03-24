import logging
from nicegui import app
from enum import Enum

class AppStorage:
    Category = Enum('Category', [('CURRENT_MODEL', 'current_model'), ('SIMPLE_MODE', 'simpleMode'), ('DARK_MODE', 'darkMode')])
    
    logger = logging.getLogger("Storage")

    def save(tag: Category, value, oid=None):
        AppStorage.logger.debug('Saving [%s] %s to %s', oid, value, tag)  
        if oid != None:
            if app.storage.user.get(oid, None) == None:
                app.storage.user[oid] = {}
            app.storage.user[oid][tag] = value
        else:
            app.storage.user[tag] = value


    def load(tag :Category, default=None, oid=None):
        if oid != None:
            oidStorage = app.storage.user.get(oid, None)
            if oidStorage != None:
                result = oidStorage.get(tag, default)
            else:
                result = None
        else:
            result = app.storage.user.get(tag, default)
        AppStorage.logger.debug('Loaded [%s] %s: %s', oid, tag, result)
        return result
    
    def refreshState(oid):
        logging.error('Refreshing state for %s', oid)
        app.storage.tab[oid]=None