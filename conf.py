import os
class Conf:
    def __init__(self):
        self.id = os.environ.get('UNO_OVERLAY_ID', '8637cb0f-df01-45bb-9782-c6d705aeff46')
        self.oid = os.environ.get('UNO_OVERLAY_OID')
        self.output = os.environ.get('UNO_OVERLAY_OUTPUT', None)
        if self.output == '':
            self.output = None
        self.darkMode = os.environ.get('APP_DARK_MODE', 'auto')
        self.multithread = os.environ.get('ENABLE_MULTITHREAD', 'true').lower() in ("yes", "true", "t", "1")
        self.logging_level = os.environ.get('LOGGING_LEVEL', 'warning').upper()
        self.cache = os.environ.get('MINIMIZE_BACKEND_USAGE', 'true').lower() in ("yes", "true", "t", "1")
        self.points = int(os.environ.get('MATCH_GAME_POINTS', 25))
        self.points_last_set = int(os.environ.get('MATCH_GAME_POINTS_LAST_SET', 15))
        self.sets = int(os.environ.get('MATCH_SETS', 5))
        
