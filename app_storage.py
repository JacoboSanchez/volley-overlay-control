import logging
from nicegui import app
from enum import Enum

# In-memory fallback storage for use outside of a NiceGUI context (e.g., during tests)
_memory_storage = {}
# Cache for the determined storage backend
_cached_storage = None

class AppStorage:
    Category = Enum('Category', [('USERNAME', 'username'), ('AUTHENTICATED', 'authenticated'), ('CONFIGURED_OUTPUT', 'configured_output'), ('CONFIGURED_OID', 'configured_oid'), ('CURRENT_MODEL', 'current_model'), ('SIMPLE_MODE', 'simpleMode'), ('DARK_MODE', 'darkMode'), ('AUTOHIDE_ENABLED', 'autohide_enabled'), ('AUTOHIDE_SECONDS', 'autohide_seconds'), ('SIMPLIFY_OPTION_ENABLED', 'simplify_option_enabled')])
    
    logger = logging.getLogger("Storage")

    def _get_storage():
        """
        Determines the appropriate storage backend and caches the result for future calls.
        """
        global _cached_storage
        if _cached_storage is not None:
            return _cached_storage
        
        try:
            if app.storage is not None:
                # This will raise a RuntimeError if not in a NiceGUI page context
                _cached_storage = app.storage.user
                logging.info('Using NiceGUI storage')
        except RuntimeError:
            # We are in a test or non-UI environment, use the in-memory fallback
            logging.info('Not using NiceGUI storage')
        if _cached_storage is None:
            logging.info('Using in-memory storage')
            _cached_storage = _memory_storage
            
        
        return _cached_storage
    
    def _reset_cache():
        """Resets the storage cache. Primarily for use in testing."""
        global _cached_storage
        _cached_storage = None


    def save(tag: Category, value, oid=None):
        storage = AppStorage._get_storage()
        AppStorage.logger.debug('Saving key %s [%s]', tag, oid)
        if oid is not None:
            if storage.get(oid) is None:
                storage[oid] = {}
            storage[oid][tag.value] = value
        else:
            storage[tag.value] = value

    def load(tag: Category, default=None, oid=None):
        storage = AppStorage._get_storage()
        AppStorage.logger.debug('Loading %s [%s] from %s', oid, tag, type(storage).__name__)
        if oid is not None:
            oid_storage = storage.get(oid, {})
            result = oid_storage.get(tag.value, default)
        else:
            result = storage.get(tag.value, default)
        AppStorage.logger.debug('Loaded %s [%s] from %s: %s', oid, tag, type(storage).__name__, result)
        return result
    
    def refresh_state(oid):
        storage = AppStorage._get_storage()
        logging.debug('Refreshing state for %s in %s', oid, type(storage).__name__)
        if oid in storage:
            if isinstance(storage, dict):
                del storage[oid]
            else: # NiceGUI storage
                storage[oid] = None

    def clear_user_storage():
        storage = AppStorage._get_storage()
        logging.info('Clearing %s', type(storage).__name__)
        storage.clear()