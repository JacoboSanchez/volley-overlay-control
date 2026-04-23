from app.env_vars_manager import EnvVarsManager


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
        self.multithread = str(EnvVarsManager.get_env_var('ENABLE_MULTITHREAD', 'true')).lower() in ("yes", "true", "t", "1")
        self.cache = str(EnvVarsManager.get_env_var('MINIMIZE_BACKEND_USAGE', 'true')).lower() in ("yes", "true", "t", "1")
        self.orderedTeams = str(EnvVarsManager.get_env_var('ORDERED_TEAMS', 'true')).lower() in ("yes", "true", "t", "1")
        self.points = int(EnvVarsManager.get_env_var('MATCH_GAME_POINTS', 25))
        self.points_last_set = int(EnvVarsManager.get_env_var('MATCH_GAME_POINTS_LAST_SET', 15))
        self.sets = int(EnvVarsManager.get_env_var('MATCH_SETS', 5))
        self.single_overlay = str(EnvVarsManager.get_env_var('SINGLE_OVERLAY_MODE', 'true')).lower() in ("yes", "true", "t", "1")
