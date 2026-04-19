import os
import json
import logging

logger = logging.getLogger(__name__)


def validate_config():
    """
    Validates critical environment variables on startup.
    Logs warnings and sets safe defaults in os.environ for invalid configurations.
    """
    # Positive integer validation
    int_vars = [
        ('MATCH_GAME_POINTS', '25'),
        ('MATCH_GAME_POINTS_LAST_SET', '15'),
        ('MATCH_SETS', '5')
    ]
    for var, default in int_vars:
        val = os.environ.get(var, default)
        try:
            int_val = int(val)
            if int_val <= 0:
                raise ValueError("Must be a positive integer")
        except ValueError:
            logger.warning("Invalid %s '%s': must be a positive integer. Defaulting to %s.", var, val, default)
            os.environ[var] = default

    # JSON validation
    json_vars = ['APP_TEAMS', 'SCOREBOARD_USERS', 'PREDEFINED_OVERLAYS', 'APP_THEMES']
    for var in json_vars:
        val = os.environ.get(var)
        if val:
            try:
                json.loads(val)
            except json.JSONDecodeError:
                logger.warning("Invalid JSON in %s. Defaulting to empty/None behavior.", var)
                # We simply remove invalid JSON from environment to prevent runtime crashes
                del os.environ[var]

    # Port / timeout integer validation
    port_val = os.environ.get('APP_PORT', '8080')
    try:
        port_int = int(port_val)
        if not (1 <= port_int <= 65535):
            raise ValueError("Out of valid port range")
    except ValueError:
        logger.warning("Invalid APP_PORT '%s': must be an integer between 1 and 65535. Defaulting to 8080.", port_val)
        os.environ['APP_PORT'] = '8080'

    timeout_val = os.environ.get('DEFAULT_HIDE_TIMEOUT', '5')
    try:
        timeout_int = int(timeout_val)
        if timeout_int <= 0:
            raise ValueError("Must be a positive integer")
    except ValueError:
        logger.warning("Invalid DEFAULT_HIDE_TIMEOUT '%s': must be a positive integer. Defaulting to 5.", timeout_val)
        os.environ['DEFAULT_HIDE_TIMEOUT'] = '5'

    # Enums validation
    dark_mode = os.environ.get('APP_DARK_MODE', 'auto').lower()
    if dark_mode not in ['on', 'off', 'auto']:
        logger.warning("Invalid APP_DARK_MODE '%s'. Must be 'on', 'off', or 'auto'. Defaulting to 'auto'.", dark_mode)
        os.environ['APP_DARK_MODE'] = 'auto'

    log_level = os.environ.get('LOGGING_LEVEL', 'info').lower()
    if log_level not in ['debug', 'info', 'warning', 'error']:
        logger.warning("Invalid LOGGING_LEVEL '%s'. Must be 'debug', 'info', 'warning', or 'error'. Defaulting to 'info'.", log_level)
        os.environ['LOGGING_LEVEL'] = 'info'
