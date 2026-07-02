from app.env_vars_manager import EnvVarsManager


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
        self.points = int(EnvVarsManager.get_env_var('MATCH_GAME_POINTS', 25))
        self.points_last_set = int(EnvVarsManager.get_env_var('MATCH_GAME_POINTS_LAST_SET', 15))
        self.sets = int(EnvVarsManager.get_env_var('MATCH_SETS', 5))
        self.set_summary_default_style = EnvVarsManager.get_env_var(
            'SET_SUMMARY_DEFAULT_STYLE', 'brand_ledger',
        )
