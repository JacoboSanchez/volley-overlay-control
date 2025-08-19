import asyncio
import logging
from nicegui import ui
from conf import Conf
from backend import Backend
from state import State
from customization import Customization
from authentication import PasswordAuthenticator
from messages import Messages
from options_dialog import OptionsDialog
from app_storage import AppStorage


class CustomizationPage:
      logger = logging.getLogger("Configuration")
       

      def __init__(self, tabs=None, configuration=None, backend=None, gui=None, options=None):
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
            self.customization = Customization(self.backend.get_current_customization())
            self.options_dialog = options
      

      def update_team_selection(self, team, logo, tname, color, textColor, selector):
            fallback_name = CustomizationPage.get_fallback_team_name(team)
            team_name = tname if tname != None else fallback_name
            teamValues = Customization.get_predefined_teams().get(team_name, None)
            if teamValues == None:
                  teamValues = Customization.get_predefined_teams()[CustomizationPage.get_fallback_team_name(team)]
            lockedColors = self.configuration.lock_teamA_colors if team == 1 else self.configuration.lock_teamB_colors
            lockedIcon = self.configuration.lock_teamA_icons if team == 1 else self.configuration.lock_teamB_icons
            ## update gui
            if lockedIcon == False:
                  logo.set_source(teamValues[Customization.TEAM_VALUES_ICON])
            if lockedColors == False:  
                  color.classes(replace=f'!bg-[{teamValues[Customization.TEAM_VALUES_COLOR]}]')
                  textColor.classes(replace=f'!bg-[{teamValues[Customization.TEAM_VALUES_TEXT_COLOR]}]')
                  selector.classes(replace=f'!bg-[{teamValues[Customization.TEAM_VALUES_COLOR]}] w-[300px]')
                  selector.classes(replace=f'!fg-[{teamValues[Customization.TEAM_VALUES_TEXT_COLOR]}] w-[300px]')
            ## update model
            self.customization.set_team_name(team, tname)
            if lockedIcon == False:
                  self.customization.set_team_logo(team, teamValues[Customization.TEAM_VALUES_ICON])
            if lockedColors == False:
                  self.customization.set_team_color(team, teamValues[Customization.TEAM_VALUES_COLOR])
                  self.customization.set_team_text_color(team, teamValues[Customization.TEAM_VALUES_TEXT_COLOR])

      def update_team_model_color(self, team, color, button, textColor=False):
            button.classes(replace=f'!bg-[{color}]')
            if textColor:
                  self.customization.set_team_text_color(team, color)
            else:
                  self.customization.set_team_color(team, color)

      def update_model_color(self, forSet, color, button, textColor=False):
            button.classes(replace=f'!bg-[{color}]')
            button.update()
            if textColor:
                  if forSet:
                        self.customization.set_set_text_color(color)
                  else:
                        self.customization.set_game_text_color(color)
            else:
                  if forSet:
                        self.customization.set_set_color(color)
                  else:
                        self.customization.set_game_color(color)


      def get_fallback_team_name(team):
            return Customization.LOCAL_NAME if team == 1 else Customization.VISITOR_NAME

      async def apply_and_refresh(self, theme_name, dialog):
            if theme_name:
                  self.customization.set_theme(theme_name)
                  dialog.close()
                  await self.reload_customization()

      async def show_theme_dialog(self):
            with ui.dialog() as dialog, ui.card():
                  ui.label(Messages.get(Messages.THEME_TITLE))
                  theme_list = self.customization.get_theme_names()
                  if not theme_list:
                        ui.label(Messages.get(Messages.NO_THEMES))
                        with ui.row():
                              ui.button(Messages.get(Messages.CLOSE), on_click=dialog.close)
                  else:
                        selection = ui.select(list(theme_list), label=Messages.get(Messages.THEME)).classes('w-[300px]').props('outlined')
                        with ui.row().classes('w-full'):
                              ui.space()
                              ui.button(Messages.get(Messages.LOAD), on_click=lambda: self.apply_and_refresh(selection.value, dialog))
                              ui.button(Messages.get(Messages.CLOSE), on_click=dialog.close)
            await dialog

      def create_team_card(self, team, teamNames):
            self.customization.set_team_logo(team, self.customization.get_team_logo(team))
            with ui.card():
                  with ui.row().classes('w-full'):
                        selector = ui.select(teamNames, 
                              new_value_mode = 'add-unique', 
                              value = self.customization.get_team_name(team),
                              key_generator=lambda k: k,
                              on_change=lambda e: self.update_team_selection(team, team_logo, e.value, team_color, team_text_color, selector)).classes('w-[300px]').props('outlined behavior=dialog label='+CustomizationPage.get_fallback_team_name(team))
                        
                  with ui.row():
                        team_logo = ui.image(self.customization.get_team_logo(team)).classes('w-9 h-9 m-auto')
                        icons_switch = ui.switch(on_change=lambda e: self.changed_icon_lock(team, icons_switch, e.value)).props('icon=no_encryption')
                        ui.space()
                        team_color = ui.button().classes('w-8 h-8 m-auto')
                        team_text_color = ui.button().classes('w-5 h-5')
                        with team_color:
                              team_color_picker = ui.color_picker(on_pick=lambda e: self.update_team_model_color(team, e.color, team_color, False))
                        team_color_picker.q_color.props('default-view=palette no-header')
                        with team_text_color:
                              team_text_color_picker = ui.color_picker(on_pick=lambda e: self.update_team_model_color(team, e.color, team_text_color, True))
                        team_text_color_picker.q_color.props('default-view=palette no-header')
                        self.update_team_model_color(team, self.customization.get_team_color(team), team_color, False)
                        self.update_team_model_color(team, self.customization.get_team_text_color(team), team_text_color, True)
                        colors_switch = ui.switch(on_change=lambda e: self.changed_color_lock(team, colors_switch, e.value)).props('icon=no_encryption')
      
      def changed_icon_lock(self, team, switch_lock, value):
            if team == 1:
                  self.configuration.lock_teamA_icons = value
            else:
                  self.configuration.lock_teamB_icons = value
            if value:
                  switch_lock.props('icon=lock')
            else:
                  switch_lock.props('icon=no_encryption')


      def changed_color_lock(self, team, switch_lock, value):
            if team == 1:
                  self.configuration.lock_teamA_colors = value
            else:
                  self.configuration.lock_teamB_colors = value
            if value:
                  switch_lock.props('icon=lock')
            else:
                  switch_lock.props('icon=no_encryption')


 
      def create_choose_color(self, name, forSet = False):
            ui.label(name)
            with ui.row():
                  main_color = ui.button().classes('w-8 h-8 m-auto')
                  main_text_color = ui.button().classes('w-5 h-5')
            with main_color:
                  main_color_picker = ui.color_picker(on_pick=lambda e: self.update_model_color(forSet, e.color, main_color, False))
            main_color_picker.q_color.props('default-view=palette no-header')
            with main_text_color:
                  main_text_color_picker = ui.color_picker(on_pick=lambda e: self.update_model_color(forSet, e.color, main_text_color, True))
            main_text_color_picker.q_color.props('default-view=palette no-header')
            self.update_model_color(forSet, self.customization.get_set_color() if forSet else self.customization.get_game_color(), main_color, False)
            self.update_model_color(forSet, self.customization.get_set_text_color() if forSet else self.customization.get_game_text_color(), main_text_color, True)
            

      def init(self, configurationTabPanel=None, force_reset=False):
            if force_reset:
                  self.customization = Customization(self.backend.get_current_customization())
            self.logger.info("Initializing")
            if configurationTabPanel != None:
                  self.container = configurationTabPanel
            if self.container != None:
                  self.container.clear()
            else:
                  logging.warning('Not container for customization...')
                  return      
            with self.container:
                  teamNames = list(Customization.get_predefined_teams())
                  if (self.configuration.orderedTeams):
                        teamNames.sort()
                  if self.customization.get_team_name(1) not in teamNames:
                        teamNames.append(self.customization.get_team_name(1))
                  if self.customization.get_team_name(2) not in teamNames:
                        teamNames.append(self.customization.get_team_name(2))
                  with ui.grid(columns=2):
                        self.create_team_card(1, teamNames)
                        self.create_team_card(2, teamNames)
                        with ui.card():
                              with ui.row():
                                    ui.switch(Messages.get(Messages.LOGOS), value=self.customization.is_show_logos(), on_change=lambda e: self.customization.set_show_logos(e.value))
                                    ui.switch(Messages.get(Messages.GRADIENT), value=self.customization.is_glossy() , on_change=lambda e: self.customization.set_glossy(e.value))
                                    if len(list(self.customization.get_theme_names())) > 0:
                                          ui.button(icon='palette', on_click=self.show_theme_dialog).props('flat')

                              with ui.row():
                                    self.create_choose_color(Messages.get(Messages.SET), True)
                                    self.create_choose_color(Messages.get(Messages.GAME), False)
                                     

                        with ui.card():
                              with ui.row().classes('place-content-center align-middle'):
                                    ui.number(label=Messages.get(Messages.HEIGHT), value=self.customization.get_height(), format='%.1f', min=0, max=100,
                                          on_change=lambda e: self.customization.set_height(f'{e.value}'))
                                    ui.space()
                                    ui.number(label=Messages.get(Messages.WIDTH), value=self.customization.get_width(), format='%.1f', min=0, max=100,
                                          on_change=lambda e: self.customization.set_width(f'{e.value}'))
                                    ui.space()
                                    ui.number(label=Messages.get(Messages.HPOS), value=self.customization.get_h_pos(), format='%.1f', min=-50, max=50,
                                          on_change=lambda e: self.customization.set_h_pos(f'{e.value}'))
                                    ui.space()
                                    ui.number(label=Messages.get(Messages.VPOS), value=self.customization.get_v_pos(), format='%.1f', min=-50, max=50,
                                          on_change=lambda e: self.customization.set_v_pos(f'{e.value}'))
                              with ui.row().classes('items-center w-full'):
                                    if AppStorage.load(AppStorage.Category.CONFIGURED_OID, None) != None:
                                          AppStorage.save(AppStorage.Category.CONFIGURED_OID, None)
                                          AppStorage.save(AppStorage.Category.CONFIGURED_OUTPUT, None)
                                          ui.link(Messages.get(Messages.RESET_LINKS), './')
                                    ui.link(Messages.get(Messages.CONTROL_LINK), 'https://app.overlays.uno/control/'+self.configuration.oid, new_tab=True)
                                    if self.configuration.output and self.configuration.output.strip():
                                          ui.link(Messages.get(Messages.OVERLAY_LINK), self.configuration.output, new_tab=True)
                                    ui.space()
                                    ui.button(icon='tune', on_click=self.options_dialog.open).props('flat').classes('text-gray-500 -ml-2 mr-2')

                                                                        
                                    
                  with ui.row().classes('w-full'):
                        ui.button(icon='keyboard_arrow_left', color='stone-500', on_click=self.switch_to_scoreboard).props('round').classes('text-white')          
                        ui.space()
                        self.dialog_reset = ui.dialog()
                        with self.dialog_reset, ui.card():
                              ui.label(Messages.get(Messages.ASK_RESET))
                              with ui.row():
                                    ui.button(color='green-500', icon='done', on_click=lambda: self.dialog_reset.submit(True))
                                    ui.button(color='red-500', icon='close', on_click=lambda: self.dialog_reset.submit(False))
                        self.dialog_reload = ui.dialog()
                        with self.dialog_reload, ui.card():
                              ui.label(Messages.get(Messages.ASK_RELOAD))
                              with ui.row():
                                    ui.button(color='green-500', icon='done', on_click=lambda: self.dialog_reload.submit(True))
                                    ui.button(color='red-500', icon='close', on_click=lambda: self.dialog_reload.submit(False))
                        ui.button(icon='save', color='blue-500', on_click=self.save).props('round').classes('text-white')
                        ui.button(icon='sync', color='emerald-600', on_click=self.ask_refresh).props('round').classes('text-white')
                        ui.button(icon='recycling', color='orange-500', on_click=self.ask_reset).props('round').classes('text-white')
                        if AppStorage.load(AppStorage.Category.USERNAME, None) != None: 
                              self.logout_dialog = ui.dialog()
                              with self.logout_dialog, ui.card():
                                    ui.label(Messages.get(Messages.ASK_LOGOUT))
                                    with ui.row():
                                          ui.button(color='green-500', icon='done', on_click=lambda: self.logout_dialog.submit(True))
                                          ui.button(color='red-500', icon='close', on_click=lambda: self.logout_dialog.submit(False))
                              ui.button(icon='logout', color='red-700', on_click=self.ask_logout).props('round').classes('text-white')

            self.logger.info("Initialized customization page")


      async def reload_customization(self):
            notification = ui.notification(timeout=None, spinner=True)
            await asyncio.sleep(0.5)
            self.init(force_reset=False)
            await asyncio.sleep(0.5)
            notification.dismiss()
    

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
            self.backend.save_json_customization(self.customization.get_model())
            self.gui.update_ui(False)
            await asyncio.sleep(0.5)
            notification.dismiss()
            self.switch_to_scoreboard()

      async def ask_logout(self):
            result = await self.logout_dialog
            if result:
                  PasswordAuthenticator.logout()

      async def ask_refresh(self):
        result = await self.dialog_reload
        if result:
            await self.refresh()

      async def ask_reset(self):
        result = await self.dialog_reset
        if result:
            notification = ui.notification(timeout=None, spinner=True)
            await asyncio.sleep(0.5)
            self.gui.reset()
            self.init(force_reset=True) 
            await asyncio.sleep(0.5)
            notification.dismiss()
            self.switch_to_scoreboard()

      def switch_to_scoreboard(self):
            self.tabs.set_value(Customization.SCOREBOARD_TAB)
      
       
