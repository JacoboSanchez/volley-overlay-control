import logging
from nicegui import app
from enum import Enum

# In-memory fallback storage for use outside of a NiceGUI context (e.g., during tests)
_memory_storage = {}
# Cache for the determined storage backend
_cached_storage = None

class AppStorage:
    Category = Enum('Category', [
        ('USERNAME', 'username'),
        ('AUTHENTICATED', 'authenticated'),
        ('CONFIGURED_OUTPUT', 'configured_output'),
        ('CONFIGURED_OID', 'configured_oid'),
        ('CURRENT_MODEL', 'current_model'),
        ('SIMPLE_MODE', 'simpleMode'),
        ('DARK_MODE', 'darkMode'),
        ('AUTOHIDE_ENABLED', 'autohide_enabled'),
        ('AUTOHIDE_SECONDS', 'autohide_seconds'),
        ('SIMPLIFY_OPTION_ENABLED', 'simplify_option_enabled'),
        ('SIMPLIFY_ON_TIMEOUT_ENABLED', 'simplify_on_timeout_enabled'),
        ('SHOW_PREVIEW', 'show_preview'),
        ('REDIRECT_PATH', 'redirect_path'),
        ('LOCK_TEAM_A_ICONS', 'lock_team_a_icons'),
        ('LOCK_TEAM_B_ICONS', 'lock_team_b_icons'),
        ('LOCK_TEAM_A_COLORS', 'lock_team_a_colors'),
        ('LOCK_TEAM_B_COLORS', 'lock_team_b_colors'),
        ('BUTTONS_FOLLOW_TEAM_COLORS', 'buttons_follow_team_colors'),
        ('TEAM_1_BUTTON_COLOR', 'team_1_button_color'),
        ('TEAM_1_BUTTON_TEXT_COLOR', 'team_1_button_text_color'),
        ('TEAM_2_BUTTON_COLOR', 'team_2_button_color'),
        ('TEAM_2_BUTTON_TEXT_COLOR', 'team_2_button_text_color'),
        ('SELECTED_FONT', 'selected_font')
    ])
    
    logger = logging.getLogger("Storage")

    def _get_storage():
        """
        Determines the appropriate storage backend.
        """
        global _cached_storage
        
        try:
            if app.storage is not None:
                # This will raise a RuntimeError if not in a NiceGUI page context
                return app.storage.user
        except RuntimeError:
            # We are in a test or non-UI environment, use the in-memory fallback
            pass
            
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
    
    def refresh_state(oid, preserve_keys=None):
        storage = AppStorage._get_storage()
        logging.debug('Refreshing state for %s in %s', oid, type(storage).__name__)
        if oid in storage:
            if preserve_keys:
                # Keep only the keys that are in preserve_keys
                preserved_data = {}
                current_data = storage[oid]
                if isinstance(current_data, dict):
                     for key in preserve_keys:
                        if key.value in current_data:
                            preserved_data[key.value] = current_data[key.value]
                
                if isinstance(storage, dict):
                    storage[oid] = preserved_data
                else: # NiceGUI storage
                    storage[oid] = preserved_data
            else:
                if isinstance(storage, dict):
                    del storage[oid]
                else: # NiceGUI storage
                    storage[oid] = None

    def clear_user_storage():
        storage = AppStorage._get_storage()
        logging.info('Clearing %s', type(storage).__name__)
        storage.clear()