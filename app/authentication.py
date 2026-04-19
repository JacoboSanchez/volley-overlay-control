import logging
import json
import secrets
from app.env_vars_manager import EnvVarsManager
from app.oid_utils import UNO_OUTPUT_BASE_URL

logger = logging.getLogger(__name__)


class PasswordAuthenticator:
    """Validates API keys against the ``SCOREBOARD_USERS`` env var."""

    _cached_users = None
    _cached_users_raw = None

    @classmethod
    def _get_users(cls):
        """Return parsed SCOREBOARD_USERS, caching the result.

        Re-parses only when the raw env var value changes.
        """
        raw = EnvVarsManager.get_env_var('SCOREBOARD_USERS', None)
        if raw == cls._cached_users_raw:
            return cls._cached_users
        cls._cached_users_raw = raw
        if not raw or not raw.strip():
            cls._cached_users = None
            return None
        try:
            cls._cached_users = json.loads(raw)
        except json.JSONDecodeError:
            cls._cached_users = None
        return cls._cached_users

    @staticmethod
    def do_authenticate_users() -> bool:
        passwords_json = EnvVarsManager.get_env_var('SCOREBOARD_USERS', None)
        return passwords_json is not None and passwords_json.strip() != ''

    @classmethod
    def get_username_for_api_key(cls, key: str):
        """Return the username whose password matches *key*, or ``None``.

        Uses ``secrets.compare_digest`` for each comparison so individual
        password checks are constant-time and don't leak a matching prefix
        via timing (see AUTHENTICATION.md §3 and PR #149 review).
        """
        users = cls._get_users()
        if users is None or not isinstance(key, str):
            return None
        for username, userconf in users.items():
            password = userconf.get("password")
            if isinstance(password, str) and secrets.compare_digest(password, key):
                return username
        return None

    @staticmethod
    def check_api_key(key: str) -> bool:
        """Check if *key* matches any configured user password."""
        return PasswordAuthenticator.get_username_for_api_key(key) is not None

    @staticmethod
    def compose_output(output: str) -> str:
        if not output.startswith(UNO_OUTPUT_BASE_URL):
            return UNO_OUTPUT_BASE_URL + output
        return output
