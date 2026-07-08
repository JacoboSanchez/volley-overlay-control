import logging

from app.env_vars_manager import EnvVarsManager

logger = logging.getLogger(__name__)


def _int_env(key: str, default: int) -> int:
    """Read an integer env var, degrading to *default* on a malformed value.

    ``Conf()`` runs during session init — a typo like ``MATCH_GAME_POINTS=abc``
    must log a warning and fall back, not crash every board with a 500.
    """
    raw = EnvVarsManager.get_env_var(key, default)
    try:
        return int(raw)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid integer for %s: %r — using default %d", key, raw, default,
        )
        return default


class Conf:
    def __init__(self):
        # Legacy layout id (used only for the championship-layout special case
        # in ``Backend.save_model``). Kept as a constant default — no env knob.
        self.id = '8637cb0f-df01-45bb-9782-c6d705aeff46'
        # ``oid`` is the *raw* overlay id — the Backend uses it to resolve the
        # overlay against the local store. ``user_id`` + ``skey`` namespace it
        # per user for local persistence (overlay state, audit log, session
        # meta, match archive). ``public_token`` is the unguessable OBS-output
        # capability token, and ``output`` is the resolved local OBS overlay
        # URL. All are populated by the session-init route for a logged-in
        # user; they stay ``None`` for bare/standalone Backend construction
        # (tests, legacy paths).
        self.oid = None
        self.user_id: int | None = None
        self.skey: str | None = None
        self.public_token: str | None = None
        self.output: str | None = None
        self.rest_user_agent = EnvVarsManager.get_env_var('REST_USER_AGENT', 'curl/8.15.0') or 'curl/8.15.0'
        self.multithread = EnvVarsManager.get_bool_env('ENABLE_MULTITHREAD', True)
        self.points = _int_env('MATCH_GAME_POINTS', 25)
        self.points_last_set = _int_env('MATCH_GAME_POINTS_LAST_SET', 15)
        self.sets = _int_env('MATCH_SETS', 5)
        self.set_summary_default_style = EnvVarsManager.get_env_var(
            'SET_SUMMARY_DEFAULT_STYLE', 'brand_ledger',
        )
