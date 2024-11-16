import os
class Conf:
    def __init__(self):
        self.id = os.environ.get('UNO_OVERLAY_ID', '8637cb0f-df01-45bb-9782-c6d705aeff46')
        self.oid = os.environ.get('UNO_OVERLAY_OID')
        self.output = os.environ.get('UNO_OVERLAY_OUTPUT', None)
        self.onair = os.environ.get('UNO_OVERLAY_AIR_ID', None)
        self.port = int(os.environ.get('APP_PORT', 8080))
        self.title= os.environ.get('APP_TITLE', 'Scoreboard')
        self.darkMode = os.environ.get('APP_DARK_MODE', 'auto')
        self.multithread = os.environ.get('ENABLE_MULTITHREAD', 'true').lower() in ("yes", "true", "t", "1")

