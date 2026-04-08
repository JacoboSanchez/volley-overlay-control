import logging
from enum import Enum

# In-memory storage (replaces the former NiceGUI per-browser storage)
_memory_storage = {}


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
    ])

    logger = logging.getLogger("Storage")

    def _get_storage():
        return _memory_storage

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
        AppStorage.logger.debug('Loading %s [%s]', oid, tag)
        if oid is not None:
            oid_storage = storage.get(oid, {})
            return oid_storage.get(tag.value, default)
        return storage.get(tag.value, default)

    def refresh_state(oid, preserve_keys=None):
        storage = AppStorage._get_storage()
        if oid in storage:
            if preserve_keys:
                preserved_data = {}
                current_data = storage[oid]
                if isinstance(current_data, dict):
                    for key in preserve_keys:
                        if key.value in current_data:
                            preserved_data[key.value] = current_data[key.value]
                storage[oid] = preserved_data
            else:
                del storage[oid]

    def clear_user_storage():
        storage = AppStorage._get_storage()
        logging.info('Clearing storage')
        storage.clear()
