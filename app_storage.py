import logging
from nicegui import app
from enum import Enum

class AppStorage:
    Category = Enum('Category', [('USERNAME', 'username'), ('AUTHENTICATED', 'authenticated'), ('CONFIGURED_OUTPUT', 'configured_output'), ('CONFIGURED_OID', 'configured_oid'), ('CURRENT_MODEL', 'current_model'), ('SIMPLE_MODE', 'simpleMode'), ('DARK_MODE', 'darkMode')])
    
    logger = logging.getLogger("Storage")

    def save(tag: Category, value, oid=None):
        AppStorage.logger.debug('Saving %s [%s]', tag, oid)  
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
        AppStorage.logger.debug('Loaded %s[%s]', oid, tag)
        return result
    
    def refresh_state(oid):
        logging.error('Refreshing state for %s', oid)
        app.storage.user[oid]=None

    def clear_user_storage():
        app.storage.user.clear()