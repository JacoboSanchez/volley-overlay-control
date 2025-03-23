import asyncio
import logging
from nicegui import ui
from conf import Conf
from backend import Backend
from state import State
from customization import Customization
from messages import Messages
from clientstorage import ClientStorage


class CustomizationPage:
      logger = logging.getLogger("Configuration")
      COLOR_FULLSCREEN_BUTTON = 'gray-400'
      COLOR_EXIT_FULLSCREEN_BUTTON = 'gray-600'

      def __init__(self, tabs=None, configuration=None, backend=None, gui=None):
            self.tabs = tabs
            if configuration != None:
                  self.configuration = configuration
            else:
                  self.configuration = Conf()
            if backend != None:
                  self.backend = backend
            else:
                  self.backend = Backend(self.configuration)
            self.gui = gui
            self.customization = Customization(self.backend.getCurrentCustomizationStateModel())

      def switch_darkmode(self, enable: bool):
            ui.dark_mode(enable)
            if enable:
                  ClientStorage.save(ClientStorage.DARK_MODE, 1)
            else:
                  ClientStorage.save(ClientStorage.DARK_MODE, 0)
            self.slider.reset()
      

      def updateTeamSelection(self, team, logo, tname, color, textColor, selector):
            fallback_name = CustomizationPage.getFallBackTeamName(team)
            team_name = tname if tname != None else fallback_name
            teamValues = Customization.getPredefinedTeams().get(team_name, None)
            if teamValues == None:
                  teamValues = Customization.getPredefinedTeams()[CustomizationPage.getFallBackTeamName(team)]
            ## update gui
            logo.set_source(teamValues[Customization.TEAM_VALUES_ICON])
            color.classes(replace=f'!bg-[{teamValues[Customization.TEAM_VALUES_COLOR]}]')
            textColor.classes(replace=f'!bg-[{teamValues[Customization.TEAM_VALUES_TEXT_COLOR]}]')
            selector.classes(replace=f'!bg-[{teamValues[Customization.TEAM_VALUES_COLOR]}]')
            selector.classes(replace=f'!fg-[{teamValues[Customization.TEAM_VALUES_TEXT_COLOR]}]')
            ## update model
            self.gui.setTeamName(team, tname)
            self.customization.setTeamLogo(team, teamValues[Customization.TEAM_VALUES_ICON])
            self.customization.setTeamColor(team, teamValues[Customization.TEAM_VALUES_COLOR])
            self.customization.setTeamTextColor(team, teamValues[Customization.TEAM_VALUES_TEXT_COLOR])

      def updateTeamModelColor(self, team, color, button, textColor=False):
            button.classes(replace=f'!bg-[{color}]')
            if textColor:
                  self.customization.setTeamTextColor(team, color)
            else:
                  self.customization.setTeamColor(team, color)

      def updateModelColor(self, forSet, color, button, textColor=False):
            button.classes(replace=f'!bg-[{color}]')
            button.update()
            if textColor:
                  if forSet:
                        self.customization.setSetTextColor(color)
                  else:
                        self.customization.setGameTextColor(color)
            else:
                  if forSet:
                        self.customization.setSetColor(color)
                  else:
                        self.customization.setGameColor(color)


      def getFallBackTeamName(team):
            return Customization.LOCAL_NAME if team == 1 else Customization.VISITOR_NAME

      def create_team_card(self, team, teamNames):
            with ui.card():
                  with ui.row():
                        team_logo = ui.image(self.customization.getTeamLogo(team)).classes('w-9 h-9 m-auto')
                        self.customization.setTeamLogo(team, self.customization.getTeamLogo(team))
                        selector = ui.select(teamNames, 
                              new_value_mode = 'add-unique', 
                              value = self.gui.getTeamName(team),
                              key_generator=lambda k: k,
                              on_change=lambda e: self.updateTeamSelection(team, team_logo, e.value, team_color, team_text_color, selector))
                        team_color = ui.button().classes('w-8 h-8 m-auto')
                        team_text_color = ui.button().classes('w-5 h-5')
                        with team_color:
                              team_color_picker = ui.color_picker(on_pick=lambda e: self.updateTeamModelColor(team, e.color, team_color, False))
                        team_color_picker.q_color.props('default-view=palette no-header')
                        with team_text_color:
                              team_text_color_picker = ui.color_picker(on_pick=lambda e: self.updateTeamModelColor(team, e.color, team_text_color, True))
                        team_text_color_picker.q_color.props('default-view=palette no-header')
                        self.updateTeamModelColor(team, self.customization.getTeamColor(team), team_color, False)
                        self.updateTeamModelColor(team, self.customization.getTeamTextColor(team), team_text_color, True)
 
      def createChooseColor(self, name, forSet = False):
            ui.label(name)
            with ui.row():
                  main_color = ui.button().classes('w-8 h-8 m-auto')
                  main_text_color = ui.button().classes('w-5 h-5')
            with main_color:
                  main_color_picker = ui.color_picker(on_pick=lambda e: self.updateModelColor(forSet, e.color, main_color, False))
            main_color_picker.q_color.props('default-view=palette no-header')
            with main_text_color:
                  main_text_color_picker = ui.color_picker(on_pick=lambda e: self.updateModelColor(forSet, e.color, main_text_color, True))
            main_text_color_picker.q_color.props('default-view=palette no-header')
            self.updateModelColor(forSet, self.customization.getSetColor() if forSet else self.customization.getGameColor(), main_color, False)
            self.updateModelColor(forSet, self.customization.getSetTextColor() if forSet else self.customization.getGameTextColor(), main_text_color, True)
            

      def init(self, configurationTabPanel=None, force_reset=False):
            if force_reset:
                  self.customization = Customization(self.backend.getCurrentCustomizationStateModel())
            self.logger.info("Initializing")
            if configurationTabPanel != None:
                  self.container = configurationTabPanel
            if self.container != None:
                  self.container.clear()
            else:
                  logging.warn('Not container for customization...')
                  return      
            with self.container:
                  teamNames = list(Customization.getPredefinedTeams())
                  if self.gui.getTeamName(1) not in teamNames:
                        teamNames.append(self.gui.getTeamName(1))
                  if self.gui.getTeamName(2) not in teamNames:
                        teamNames.append(self.gui.getTeamName(2))
                  
                  with ui.grid(columns=2):
                        self.create_team_card(1, teamNames)
                        self.create_team_card(2, teamNames)
                        with ui.card():
                              with ui.row():
                                    ui.switch(Messages.LOGOS, value=self.gui.isShowLogos(), on_change=lambda e: self.gui.setShowLogos(e.value))
                                    ui.switch(Messages.FLAT_COLOR, value=not self.customization.isGlossy() , on_change=lambda e: self.customization.setGlossy(not e.value))
                                    self.slider = ui.slide_item()
                                    with self.slider:
                                          with ui.item():
                                                with ui.item_section():
                                                      with ui.row():
                                                            ui.icon('dark_mode')      
                                                            ui.icon('multiple_stop')
                                                            ui.icon('light_mode', color='amber')
                                          with self.slider.right( color='black', on_slide=lambda: self.switch_darkmode(True)):
                                                ui.icon('dark_mode')
                                          with self.slider.left(color='white', on_slide=lambda: self.switch_darkmode(False)):
                                                ui.icon('light_mode', color='amber')
                              with ui.row():
                                    self.createChooseColor(Messages.SET, True)
                                    self.createChooseColor(Messages.GAME, False)
                                    fullscreen = ui.fullscreen(on_value_change=self.fullScreenUpdated)
                                    ui.space()
                                    self.fullscreenButton = ui.button(icon='fullscreen', color=self.COLOR_FULLSCREEN_BUTTON, on_click=fullscreen.toggle).props('outline round color='+self.COLOR_FULLSCREEN_BUTTON)
                        with ui.card():
                              with ui.row().classes('place-content-center align-middle'):
                                    ui.number(label=Messages.HEIGHT, value=self.customization.getHeight(), format='%.1f', min=0, max=100,
                                          on_change=lambda e: self.customization.setHeight(f'{e.value}'))
                                    ui.space()
                                    ui.number(label=Messages.WIDTH, value=self.customization.getWidth(), format='%.1f', min=0, max=100,
                                          on_change=lambda e: self.customization.setWidth(f'{e.value}'))
                                    ui.space()
                                    ui.number(label=Messages.HPOS, value=self.customization.getHPos(), format='%.1f', min=-50, max=50,
                                          on_change=lambda e: self.customization.setHPos(f'{e.value}'))
                                    ui.space()
                                    ui.number(label=Messages.VPOS, value=self.customization.getVPos(), format='%.1f', min=-50, max=50,
                                          on_change=lambda e: self.customization.setVPos(f'{e.value}'))
                              with ui.row():
                                    if self.configuration.output != None:
                                          ui.link(Messages.OVERLAY_LINK, self.configuration.output, new_tab=True)
                                    ui.link(Messages.CONTROL_LINK, 'https://app.overlays.uno/control/'+self.configuration.oid, new_tab=True)

                                    
                  with ui.row().classes('w-full'):
                        ui.button(icon='keyboard_arrow_left', color='stone-500', on_click=self.swithToScoreboard).props('round').classes('text-white')          
                        ui.space()
                        
                        self.dialog = ui.dialog()
                        with self.dialog, ui.card():
                              ui.label('Reset?')
                              with ui.row():
                                    ui.button(color='green-500', icon='done', on_click=lambda: self.dialog.submit(True))
                                    ui.button(color='red-500', icon='close', on_click=lambda: self.dialog.submit(False))
                        ui.button(icon='save', color='blue-500', on_click=self.save).props('round').classes('text-white')
                        ui.button(icon='sync', color='emerald-600', on_click=self.refresh).props('round').classes('text-white')
                        ui.button(icon='recycling', color='red-700', on_click=self.askReset).props('round').classes('text-white')
            self.logger.info("Initialized customization page")

      def fullScreenUpdated(self, e):
            if e.value:
                 self.fullscreenButton.icon = 'fullscreen_exit'
                 self.fullscreenButton.props('color='+self.COLOR_EXIT_FULLSCREEN_BUTTON)
            else:
                  self.fullscreenButton.icon = 'fullscreen'
                  self.fullscreenButton.props('color='+self.COLOR_FULLSCREEN_BUTTON)

      async def refresh(self):
            notification = ui.notification(timeout=None, spinner=True)
            await asyncio.sleep(0.5)
            self.gui.refresh()
            self.init(force_reset=True)
            await asyncio.sleep(0.5)
            notification.dismiss()

      async def save(self):
            notification = ui.notification(timeout=None, spinner=True)
            await asyncio.sleep(0.5)
            state_model = self.gui.getCurrentModel()
            sub_model = {clave: state_model[clave] for clave in [State.A_TEAM, State.B_TEAM, State.LOGOS_BOOL] if clave in state_model}
            self.backend.saveJSONState(sub_model)
            self.backend.saveJSONCustomization(self.customization.getModel())
            self.gui.updateUI(False)
            await asyncio.sleep(0.5)
            notification.dismiss()
            self.swithToScoreboard()

      async def askReset(self):
        result = await self.dialog
        if result:
            self.gui.reset()
            self.init(force_reset=True) 
            self.swithToScoreboard()

      def swithToScoreboard(self):
            self.tabs.set_value(Customization.SCOREBOARD_TAB)
