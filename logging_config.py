import logging
import sys
import os

def setup_logging():
    """
    Configures the format and level of logging for the application.
    """
    logging.addLevelName(logging.DEBUG, "\033[39m%s\033[1;0m" % logging.getLevelName(logging.DEBUG))
    logging.addLevelName(logging.INFO, "\033[1;33m%s\033[1;0m" % logging.getLevelName(logging.INFO))
    logging.addLevelName(logging.WARNING, "\033[1;43m%s\033[1;0m" % logging.getLevelName(logging.WARNING))
    logging.addLevelName(logging.ERROR, "\033[1;31m%s\033[1;0m" % logging.getLevelName(logging.ERROR))
    logging.addLevelName(logging.FATAL, "\033[1;41m%s\033[1;0m" % logging.getLevelName(logging.FATAL))
    
    root = logging.getLogger()
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter("\033[1;36m%s\033[1;0m" % '%(asctime)s' + ' %(levelname)s ' + "\033[32m%s\033[1;0m" % '[%(name)s]' + ':  %(message)s')
    handler.setFormatter(formatter)
    
    # Removing previous handlers to prevent duplication
    if root.hasHandlers():
        root.handlers.clear()
        
    root.addHandler(handler)
    
    log_level = os.environ.get('LOGGING_LEVEL', 'warning').upper()
    root.setLevel(log_level)