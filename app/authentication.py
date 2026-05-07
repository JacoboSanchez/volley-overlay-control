import hashlib
import json
import logging
import threading
import time

from app.env_vars_manager import EnvVarsManager
from app.oid_utils import UNO_OUTPUT_BASE_URL
from app.password_hash import is_hashed, verify_password

logger = logging.getLogger(__name__)


class PasswordAuthenticator:
    """Validates API keys against the ``SCOREBOARD_USERS`` env var.

    Each user entry may carry either ``password`` (plaintext) or
    ``password_hash`` (a scrypt record produced by
    :mod:`app.password_hash`). When both are present, the hash wins —
    operators in the middle of a migration shouldn't have to delete the
    plaintext value to switch over.

    Hash verification is intentionally slow (~50 ms per check at the
    default scrypt parameters), so a per-process cache short-circuits
    repeat lookups within a 60-second TTL. The cache is keyed on the
    SHA-256 of the *provided* token so the cleartext value never sits
    in memory beyond the request that produced it. The cache is
    flushed automatically whenever :data:`SCOREBOARD_USERS` changes —
    a removed user's previously-cached entry stops being trusted on
    the very next ``_get_users`` call.
    """

    _cached_users = None
    _cached_users_raw = None
    _verify_cache: dict = {}
    _verify_cache_lock = threading.Lock()
    _VERIFY_CACHE_TTL = 60.0
    _VERIFY_CACHE_MAX = 256

    @classmethod
    def _get_users(cls):
        """Return parsed SCOREBOARD_USERS, caching the result.

        Re-parses only when the raw env var value changes. Any change
        also flushes the verify cache so a removed user can't stay
        authenticated past the env-var rotation.

        Returns ``None`` for any malformed payload — invalid JSON,
        a top-level JSON value that isn't an object, etc. — so every
        caller can assume the cached value is either ``None`` or a
        ``dict`` and skip the type check.
        """
        raw = EnvVarsManager.get_env_var('SCOREBOARD_USERS', None)
        if raw == cls._cached_users_raw:
            return cls._cached_users
        cls._cached_users_raw = raw
        with cls._verify_cache_lock:
            cls._verify_cache.clear()
        if not raw or not raw.strip():
            cls._cached_users = None
            return None
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            cls._cached_users = None
            return None
        if not isinstance(parsed, dict):
            # ``SCOREBOARD_USERS=[]`` or any other non-object payload
            # would later trip ``.items()`` / ``.get()``; reject at
            # the cache boundary so callers can trust the type.
            logger.warning(
                "SCOREBOARD_USERS top-level JSON value must be an object; "
                "got %s — treating as no users configured.",
                type(parsed).__name__,
            )
            cls._cached_users = None
            return None
        cls._cached_users = parsed
        return cls._cached_users

    @staticmethod
    def do_authenticate_users() -> bool:
        passwords_json = EnvVarsManager.get_env_var('SCOREBOARD_USERS', None)
        return passwords_json is not None and passwords_json.strip() != ''

    @classmethod
    def _cache_hit(cls, key_hash: str, users: dict, now: float):
        cached = cls._verify_cache.get(key_hash)
        if cached is None:
            return None
        username, expires_at = cached
        if expires_at <= now or username not in users:
            # Stale entry — drop it lazily.
            cls._verify_cache.pop(key_hash, None)
            return None
        return username

    @classmethod
    def _cache_store(cls, key_hash: str, username: str, now: float) -> None:
        cls._verify_cache[key_hash] = (username, now + cls._VERIFY_CACHE_TTL)
        if len(cls._verify_cache) > cls._VERIFY_CACHE_MAX:
            # Evict the entry with the soonest expiry — bounded
            # memory without paying for an LRU structure.
            soonest = min(
                cls._verify_cache.items(), key=lambda kv: kv[1][1],
            )
            cls._verify_cache.pop(soonest[0], None)

    @classmethod
    def get_username_for_api_key(cls, key: str):
        """Return the username whose credential matches *key*, or ``None``.

        Verification accepts either the legacy ``password`` (plaintext)
        or the new ``password_hash`` (scrypt) on each user entry.
        Successful verifications are cached for
        :data:`_VERIFY_CACHE_TTL` seconds so the per-request cost
        stays negligible even with hashed credentials.
        """
        users = cls._get_users()
        # ``_get_users`` already guarantees ``None`` or ``dict``, but
        # the explicit ``isinstance`` makes the contract obvious to
        # static analysis and future refactors.
        if not isinstance(users, dict) or not isinstance(key, str):
            return None

        key_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()
        now = time.monotonic()
        with cls._verify_cache_lock:
            cached = cls._cache_hit(key_hash, users, now)
            if cached is not None:
                return cached

        for username, userconf in users.items():
            # A ``SCOREBOARD_USERS`` payload like ``{"alice": "secret"}``
            # would parse fine but trip ``userconf.get`` if we trusted
            # the dict shape. Skip non-object entries.
            if not isinstance(userconf, dict):
                continue
            stored = userconf.get("password_hash") or userconf.get("password")
            if not isinstance(stored, str) or not stored:
                continue
            if verify_password(key, stored):
                with cls._verify_cache_lock:
                    cls._cache_store(key_hash, username, now)
                return username
        return None

    @staticmethod
    def check_api_key(key: str) -> bool:
        """Check if *key* matches any configured user credential."""
        return PasswordAuthenticator.get_username_for_api_key(key) is not None

    @staticmethod
    def has_hashed_credentials() -> bool:
        """Return True iff at least one user entry uses ``password_hash``.

        Exposed for the startup audit log: an operator who has half-
        migrated a user list can quickly confirm which entries are
        still on plaintext.
        """
        users = PasswordAuthenticator._get_users()
        if not isinstance(users, dict):
            return False
        for cfg in users.values():
            if isinstance(cfg, dict) and is_hashed(cfg.get("password_hash")):
                return True
        return False

    @staticmethod
    def compose_output(output: str) -> str:
        if not output.startswith(UNO_OUTPUT_BASE_URL):
            return UNO_OUTPUT_BASE_URL + output
        return output
