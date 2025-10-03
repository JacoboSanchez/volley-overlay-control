from app.env_vars_manager import EnvVarsManager
from app.app_storage import AppStorage

class Conf:
    def __init__(self):
        self.id = EnvVarsManager.get_env_var('UNO_OVERLAY_ID', '8637cb0f-df01-45bb-9782-c6d705aeff46')
        self.oid = EnvVarsManager.get_env_var('UNO_OVERLAY_OID', None)
        self.output = EnvVarsManager.get_env_var('UNO_OVERLAY_OUTPUT', None)
        if self.output == '':
            self.output = None
        self.rest_user_agent = EnvVarsManager.get_env_var('REST_USER_AGENT', 'curl/8.15.0')
        if self.rest_user_agent == '':
            self.rest_user_agent = 'curl/8.15.0'
        self.darkMode = EnvVarsManager.get_env_var('APP_DARK_MODE', 'auto')
        self.multithread = str(EnvVarsManager.get_env_var('ENABLE_MULTITHREAD', 'true')).lower() in ("yes", "true", "t", "1")
        self.cache = str(EnvVarsManager.get_env_var('MINIMIZE_BACKEND_USAGE', 'true')).lower() in ("yes", "true", "t", "1")
        self.orderedTeams = str(EnvVarsManager.get_env_var('ORDERED_TEAMS', 'true')).lower() in ("yes", "true", "t", "1")
        self.points = int(EnvVarsManager.get_env_var('MATCH_GAME_POINTS', 25))
        self.points_last_set = int(EnvVarsManager.get_env_var('MATCH_GAME_POINTS_LAST_SET', 15))
        self.sets = int(EnvVarsManager.get_env_var('MATCH_SETS', 5))
        self.single_overlay = str(EnvVarsManager.get_env_var('SINGLE_OVERLAY_MODE', 'true')).lower() in ("yes", "true", "t", "1")
        self.disable_overview = str(EnvVarsManager.get_env_var('DISABLE_OVERVIEW', 'false')).lower() in ("yes", "true", "t", "1")

    @property
    def lock_teamA_icons(self):
        return AppStorage.load(AppStorage.Category.LOCK_TEAM_A_ICONS, oid=self.oid, default=False)

    @property
    def lock_teamB_icons(self):
        return AppStorage.load(AppStorage.Category.LOCK_TEAM_B_ICONS, oid=self.oid, default=False)

    @property
    def lock_teamA_colors(self):
        return AppStorage.load(AppStorage.Category.LOCK_TEAM_A_COLORS, oid=self.oid, default=False)

    @property
    def lock_teamB_colors(self):
        return AppStorage.load(AppStorage.Category.LOCK_TEAM_B_COLORS, oid=self.oid, default=False)

    @property
    def show_preview(self):
        stored = AppStorage.load(AppStorage.Category.SHOW_PREVIEW, oid=self.oid)
        if stored is not None:
            return stored
        return EnvVarsManager.get_env_var('SHOW_PREVIEW', 'false')

    @property
    def auto_hide(self):
        stored = AppStorage.load(AppStorage.Category.AUTOHIDE_ENABLED, oid=self.oid)
        if stored is not None:
            return stored
        return str(EnvVarsManager.get_env_var('AUTO_HIDE_ENABLED', 'false')).lower() in ("yes", "true", "t", "1")

    @property
    def hide_timeout(self):
        stored = AppStorage.load(AppStorage.Category.AUTOHIDE_SECONDS, oid=self.oid)
        if stored is not None:
            return int(stored)
        return int(EnvVarsManager.get_env_var('DEFAULT_HIDE_TIMEOUT', 5))

    @property
    def auto_simple_mode(self):
        stored = AppStorage.load(AppStorage.Category.SIMPLIFY_OPTION_ENABLED, oid=self.oid)
        if stored is not None:
            return stored
        return str(EnvVarsManager.get_env_var('AUTO_SIMPLE_MODE', 'false')).lower() in ("yes", "true", "t", "1")

    @property
    def auto_simple_mode_timeout(self):
        stored = AppStorage.load(AppStorage.Category.SIMPLIFY_ON_TIMEOUT_ENABLED, oid=self.oid)
        if stored is not None:
            return stored
        return str(EnvVarsManager.get_env_var('AUTO_SIMPLE_MODE_TIMEOUT', 'false')).lower() in ("yes", "true", "t", "1")