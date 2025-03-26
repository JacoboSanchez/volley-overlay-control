import customization_page
import logging
import os
import sys
import asyncio
from oid_dialog import OidDialog
from gui import GUI
from nicegui import ui
from customization import Customization
from customization_page import CustomizationPage
from conf import Conf
from backend import Backend
from app_storage import AppStorage

logging.addLevelName( logging.DEBUG, "\033[33m%s\033[1;0m" % logging.getLevelName(logging.DEBUG))
logging.addLevelName( logging.INFO, "\033[1;33m%s\033[1;0m" % logging.getLevelName(logging.INFO))
logging.addLevelName( logging.WARNING, "\033[1;31m%s\033[1;0m" % logging.getLevelName(logging.WARNING))
logging.addLevelName( logging.ERROR, "\033[1;41m%s\033[1;0m" % logging.getLevelName(logging.ERROR))
root = logging.getLogger()
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter( "\033[1;36m%s\033[1;0m" % '%(asctime)s'+' %(levelname)s '+"\033[32m%s\033[1;0m" % '[%(name)s]'+':  %(message)s'))
root.addHandler(handler)
root.setLevel(os.environ.get('LOGGING_LEVEL', 'debug').upper())


logger = logging.getLogger("Main")

scoreboardTab = ui.tab(Customization.SCOREBOARD_TAB)
configurationTab = ui.tab(Customization.CONFIG_TAB)

def resetLinksStorage():
    logger.info("resetting links")
    AppStorage.save(AppStorage.Category.CONFIGURED_OID, None)
    AppStorage.save(AppStorage.Category.CONFIGURED_OUTPUT, None)

@ui.page("/indoor")
async def beach(control=None, output=None, refresh=None):
    if refresh == "true":
        resetLinksStorage()
        ui.navigate.to('./')
    await runPage(custom_points_limit=25, custom_points_limit_last_set=15, custom_sets_limit=5, oid=control, output=output)

@ui.page("/beach")
async def beach(control=None, output=None, refresh=None):
    if refresh == "true":
        resetLinksStorage()
        ui.navigate.to('./')
    await runPage(custom_points_limit=21, custom_points_limit_last_set=15, custom_sets_limit=3, oid=control, output=output)

@ui.page("/")
async def main(control=None, output=None, refresh=None): 
    if refresh == "true":
        resetLinksStorage()
        ui.navigate.to('./')
    await runPage(oid=control, output=output)


async def runPage(custom_points_limit=None, custom_points_limit_last_set=None, custom_sets_limit=None, oid=None, output=None):
    await ui.context.client.connected()
    conf = Conf()
    if custom_points_limit == None:
        custom_points_limit = conf.points
    if custom_points_limit_last_set == None:
        custom_points_limit_last_set = conf.points_last_set
    if custom_sets_limit == None:
        custom_sets_limit = conf.sets
    if oid != None:
        conf.oid = oid
        conf.output = None
    if output != None:
        conf.output = OidDialog.UNO_OUTPUT_BASE_URL+output
    
    if not Backend.validOid(conf.oid):
        storageOid = AppStorage.load(AppStorage.Category.CONFIGURED_OID, default=None)
        storageOutput = AppStorage.load(AppStorage.Category.CONFIGURED_OUTPUT, default=None)
        if Backend.validOid(storageOid):
            logger.info("Loading session oid: %s and output %s", storageOid, storageOutput)
            conf.oid = storageOid
            conf.output = storageOutput
        else:
            logger.info("Current oid is not valid: %s", conf.oid)
            dialog = OidDialog()
            await dialog.open()
            
            result = dialog.get_result()
            if result != None:
                conf.oid = result[OidDialog.CONTROL_TOKEN_KEY]
                if result[OidDialog.OUTPUT_URL_KEY] != None:
                    conf.output = result[OidDialog.OUTPUT_URL_KEY]
                logger.debug("Received oid %s and output", conf.oid, conf.output)
                AppStorage.save(AppStorage.Category.CONFIGURED_OID, conf.oid)
                AppStorage.save(AppStorage.Category.CONFIGURED_OUTPUT, conf.output)
                
    notification = ui.notification(timeout=None, spinner=True)
    backend = Backend(conf)
    tabs = ui.tabs().props('horizontal').classes("w-full")
    scoreboard_page = GUI(tabs, conf, backend)
    customization_page = CustomizationPage(tabs, conf, backend, scoreboard_page)
    with ui.tab_panels(tabs, value=scoreboardTab).classes("w-full"):
        scoreboardTabPanel = ui.tab_panel(scoreboardTab)
        with scoreboardTabPanel:
            scoreboard_page.init(custom_points_limit=custom_points_limit, custom_points_limit_last_set=custom_points_limit_last_set, custom_sets_limit=custom_sets_limit)
        configurationTabPanel = ui.tab_panel(configurationTab)
        with configurationTabPanel:
            customization_page.init(configurationTabPanel)
    with tabs:
        scoreboardTab
        configurationTab
    notification.dismiss()

onair = os.environ.get('UNO_OVERLAY_AIR_ID', None)
if onair == '':
    onair = None
port = int(os.environ.get('APP_PORT', 8080))
title = os.environ.get('APP_TITLE', 'Scoreboard')
secret = os.environ.get('STORAGE_SECRET', title+str(port))
custom_favicon='<svg xmlns="http://www.w3.org/2000/svg" enable-background="new 0 0 24 24" height="24px" viewBox="0 0 24 24" width="24px" fill="#5f6368"><g><rect fill="none" height="24" width="24"/></g><g><g><path d="M12,2C6.48,2,2,6.48,2,12c0,5.52,4.48,10,10,10s10-4.48,10-10C22,6.48,17.52,2,12,2z M13,4.07 c3.07,0.38,5.57,2.52,6.54,5.36L13,5.65V4.07z M8,5.08c1.18-0.69,3.33-1.06,3-1.02v7.35l-3,1.73V5.08z M4.63,15.1 C4.23,14.14,4,13.1,4,12c0-2.02,0.76-3.86,2-5.27v7.58L4.63,15.1z M5.64,16.83L12,13.15l3,1.73l-6.98,4.03 C7.09,18.38,6.28,17.68,5.64,16.83z M10.42,19.84 M12,20c-0.54,0-1.07-0.06-1.58-0.16l6.58-3.8l1.36,0.78 C16.9,18.75,14.6,20,12,20z M13,11.42V7.96l7,4.05c0,1.1-0.23,2.14-0.63,3.09L13,11.42z"/></g></g></svg>'
ui.run(title=title, favicon=custom_favicon, on_air=onair, port=port, storage_secret=secret)