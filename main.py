import conf
import customization_page
from gui import GUI
from nicegui import ui
from customization import Customization
from customization_page import CustomizationPage
from conf import Conf
from backend import Backend


conf = Conf()
backend = Backend(conf)
tabs = ui.tabs().props('horizontal').classes("w-full")
scoreboardTab = ui.tab(Customization.SCOREBOARD_TAB)
configurationTab = ui.tab(Customization.CONFIG_TAB)
gui = GUI(tabs, conf, backend)
customization_page = CustomizationPage(tabs, conf, backend, gui)

@ui.page("/indoor")
def beach():
    runPage(custom_points_limit=25, custom_points_limit_last_set=15, custom_sets_limit=5)

@ui.page("/beach")
def beach():
    runPage(custom_points_limit=21, custom_points_limit_last_set=15, custom_sets_limit=3)


@ui.page("/")
def main():
    runPage(custom_points_limit=conf.points, custom_points_limit_last_set=conf.points_last_set, custom_sets_limit=conf.sets)
    
def runPage(custom_points_limit=None, custom_points_limit_last_set=None, custom_sets_limit=None):
    with ui.tab_panels(tabs, value=scoreboardTab).classes("w-full"):
        scoreboardTabPanel = ui.tab_panel(scoreboardTab)
        with scoreboardTabPanel:
            gui.init(custom_points_limit=custom_points_limit, custom_points_limit_last_set=custom_points_limit_last_set, custom_sets_limit=custom_sets_limit)
        configurationTabPanel = ui.tab_panel(configurationTab)
        with configurationTabPanel:
            customization_page.init(configurationTabPanel)
    with tabs:
        scoreboardTab
        configurationTab

custom_favicon='<svg xmlns="http://www.w3.org/2000/svg" enable-background="new 0 0 24 24" height="24px" viewBox="0 0 24 24" width="24px" fill="#5f6368"><g><rect fill="none" height="24" width="24"/></g><g><g><path d="M12,2C6.48,2,2,6.48,2,12c0,5.52,4.48,10,10,10s10-4.48,10-10C22,6.48,17.52,2,12,2z M13,4.07 c3.07,0.38,5.57,2.52,6.54,5.36L13,5.65V4.07z M8,5.08c1.18-0.69,3.33-1.06,3-1.02v7.35l-3,1.73V5.08z M4.63,15.1 C4.23,14.14,4,13.1,4,12c0-2.02,0.76-3.86,2-5.27v7.58L4.63,15.1z M5.64,16.83L12,13.15l3,1.73l-6.98,4.03 C7.09,18.38,6.28,17.68,5.64,16.83z M10.42,19.84 M12,20c-0.54,0-1.07-0.06-1.58-0.16l6.58-3.8l1.36,0.78 C16.9,18.75,14.6,20,12,20z M13,11.42V7.96l7,4.05c0,1.1-0.23,2.14-0.63,3.09L13,11.42z"/></g></g></svg>'
ui.run(title=conf.title, favicon=custom_favicon, on_air=conf.onair, port=conf.port)