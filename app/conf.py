from app.env_vars_manager import EnvVarsManager


class Conf:
    def __init__(self) -> None:
        # ``oid`` is the *raw* overlay id — the Backend uses it to resolve the
        # overlay against the local store. ``user_id`` + ``skey`` namespace it
        # per user for local persistence (overlay state, audit log, session
        # meta, match archive). ``public_token`` is the unguessable OBS-output
        # capability token, and ``output`` is the resolved local OBS overlay
        # URL. All are populated by the session-init route for a logged-in
        # user; they stay ``None`` for bare/standalone Backend construction
        # (tests, legacy paths).
        self.oid: str | None = None
        self.user_id: int | None = None
        self.skey: str | None = None
        self.public_token: str | None = None
        self.output: str | None = None
        self.multithread = EnvVarsManager.get_bool_env('ENABLE_MULTITHREAD', True)
        # ``Conf()`` runs during session init, so a typo like
        # ``MATCH_GAME_POINTS=abc`` (or a negative value) must warn and fall
        # back rather than crash every board with a 500.
        self.points = EnvVarsManager.get_int_env('MATCH_GAME_POINTS', 25, minimum=1)
        self.points_last_set = EnvVarsManager.get_int_env(
            'MATCH_GAME_POINTS_LAST_SET', 15, minimum=1,
        )
        self.sets = EnvVarsManager.get_int_env('MATCH_SETS', 5, minimum=1)
        self.set_summary_default_style = EnvVarsManager.get_env_var(
            'SET_SUMMARY_DEFAULT_STYLE', 'brand_ledger',
        )
