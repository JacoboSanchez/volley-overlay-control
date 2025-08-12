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

      def __init__(self, tabs=None, configuration: Conf = None, backend: Backend = None, gui=None, options=None):
            self.tabs = tabs
            self.configuration = configuration or Conf()
            self.backend = backend or Backend(self.configuration)
            self.gui = gui
            self.customization = Customization(self.backend.get_current_customization())
            self.options_dialog = options

      def init(self, configurationTabPanel=None, force_reset=False):
            if force_reset:
                  self.customization = Customization(self.backend.get_current_customization())
            self.logger.info("Initializing Customization Page")

            if configurationTabPanel is None:
                  logging.warning('No container for customization provided.')
                  return
            self.container = configurationTabPanel
            self.container.clear()

            with self.container:
                  team_names = self._prepare_team_names()
                  with ui.grid(columns=2):
                        self._create_team_cards(team_names)
                        self._create_general_settings_card()
                        self._create_positioning_and_links_card()
                  self._create_action_buttons()
                  self._create_dialogs()

            self.logger.info("Customization page initialized")

      def _prepare_team_names(self):
            team_names = list(Customization.get_predefined_teams())
            if self.configuration.orderedTeams:
                  team_names.sort()
            for i in range(1, 3):
                  team_name = self.customization.get_team_name(i)
                  if team_name not in team_names:
                        team_names.append(team_name)
            return team_names

      def _create_team_cards(self, team_names):
            self.create_team_card(1, team_names)
            self.create_team_card(2, team_names)

      def _create_general_settings_card(self):
            with ui.card():
                  with ui.row():
                        ui.switch(Messages.get(Messages.LOGOS), value=self.customization.is_show_logos(), on_change=lambda e: self.customization.set_show_logos(e.value))
                        ui.switch(Messages.get(Messages.GRADIENT), value=self.customization.is_glossy(), on_change=lambda e: self.customization.set_glossy(e.value))
                  with ui.row():
                        self.create_choose_color(Messages.get(Messages.SET), True)
                        self.create_choose_color(Messages.get(Messages.GAME), False)

      def _create_positioning_and_links_card(self):
            with ui.card():
                  with ui.row().classes('place-content-center align-middle'):
                        self._create_number_input(Messages.HEIGHT, self.customization.get_height(), self.customization.set_height)
                        ui.space()
                        self._create_number_input(Messages.WIDTH, self.customization.get_width(), self.customization.set_width)
                        ui.space()
                        self._create_number_input(Messages.HPOS, self.customization.get_h_pos(), self.customization.set_h_pos, -50, 50)
                        ui.space()
                        self._create_number_input(Messages.VPOS, self.customization.get_v_pos(), self.customization.set_v_pos, -50, 50)
                  with ui.row().classes('items-center w-full'):
                        if AppStorage.load(AppStorage.Category.CONFIGURED_OID):
                              ui.link(Messages.get(Messages.RESET_LINKS), './?refresh=true')
                        ui.link(Messages.get(Messages.CONTROL_LINK), f'https://app.overlays.uno/control/{self.configuration.oid}', new_tab=True)
                        if self.configuration.output and self.configuration.output.strip():
                              ui.link(Messages.get(Messages.OVERLAY_LINK), self.configuration.output, new_tab=True)
                        ui.space()
                        ui.button(icon='tune', on_click=self.options_dialog.open).props('flat').classes('text-gray-500 -ml-2 mr-2')

      def _create_number_input(self, label, value, on_change, min_val=0, max_val=100):
            ui.number(label=Messages.get(label), value=value, format='%.1f', min=min_val, max=max_val,
                      on_change=lambda e: on_change(f'{e.value}'))

      def _prepare_team_names(self):
            team_names = list(Customization.get_predefined_teams())
            if self.configuration.orderedTeams:
                  team_names.sort()
            for i in range(1, 3):
                  team_name = self.customization.get_team_name(i)
                  if team_name not in team_names:
                        team_names.append(team_name)
            return team_names

      def _create_team_cards(self, team_names):
            self.create_team_card(1, team_names)
            self.create_team_card(2, team_names)

      def _create_general_settings_card(self):
            with ui.card():
                  with ui.row():
                        ui.switch(Messages.get(Messages.LOGOS), value=self.customization.is_show_logos(), on_change=lambda e: self.customization.set_show_logos(e.value))
                        ui.switch(Messages.get(Messages.GRADIENT), value=self.customization.is_glossy(), on_change=lambda e: self.customization.set_glossy(e.value))
                  with ui.row():
                        self.create_choose_color(Messages.get(Messages.SET), True)
                        self.create_choose_color(Messages.get(Messages.GAME), False)

      def _create_positioning_card(self):
            with ui.card():
                  with ui.row().classes('place-content-center align-middle'):
                        self._create_number_input(Messages.HEIGHT, self.customization.get_height(), self.customization.set_height)
                        ui.space()
                        self._create_number_input(Messages.WIDTH, self.customization.get_width(), self.customization.set_width)
                        ui.space()
                        self._create_number_input(Messages.HPOS, self.customization.get_h_pos(), self.customization.set_h_pos, -50, 50)
                        ui.space()
                        self._create_number_input(Messages.VPOS, self.customization.get_v_pos(), self.customization.set_v_pos, -50, 50)

      def _create_number_input(self, label, value, on_change, min_val=0, max_val=100):
            ui.number(label=Messages.get(label), value=value, format='%.1f', min=min_val, max=max_val,
                      on_change=lambda e: on_change(f'{e.value}'))

      def _create_links_and_options_card(self):
            with ui.card():
                  with ui.row().classes('items-center w-full'):
                        if AppStorage.load(AppStorage.Category.CONFIGURED_OID):
                              ui.link(Messages.get(Messages.RESET_LINKS), './?refresh=true')
                        ui.link(Messages.get(Messages.CONTROL_LINK), f'https://app.overlays.uno/control/{self.configuration.oid}', new_tab=True)
                        if self.configuration.output and self.configuration.output.strip():
                              ui.link(Messages.get(Messages.OVERLAY_LINK), self.configuration.output, new_tab=True)
                        ui.space()
                        ui.button(icon='tune', on_click=self.options_dialog.open).props('flat').classes('text-gray-500 -ml-2 mr-2')

      def _create_action_buttons(self):
            with ui.row().classes('w-full'):
                  ui.button(icon='keyboard_arrow_left', color='stone-500', on_click=self.switch_to_scoreboard).props('round').classes('text-white')
                  ui.space()
                  ui.button(icon='save', color='blue-500', on_click=self.save).props('round').classes('text-white')
                  ui.button(icon='sync', color='emerald-600', on_click=self.ask_refresh).props('round').classes('text-white')
                  ui.button(icon='recycling', color='orange-500', on_click=self.ask_reset).props('round').classes('text-white')
                  if AppStorage.load(AppStorage.Category.USERNAME):
                        ui.button(icon='logout', color='red-700', on_click=self.ask_logout).props('round').classes('text-white')

      def _create_dialogs(self):
            self.dialog_reset = self._create_dialog(Messages.ASK_RESET)
            self.dialog_reload = self._create_dialog(Messages.ASK_RELOAD)
            if AppStorage.load(AppStorage.Category.USERNAME):
                  self.logout_dialog = self._create_dialog(Messages.ASK_LOGOUT)

      def _create_dialog(self, message):
            dialog = ui.dialog()
            with dialog, ui.card():
                  ui.label(Messages.get(message))
                  with ui.row():
                        ui.button(color='green-500', icon='done', on_click=lambda: dialog.submit(True))
                        ui.button(color='red-500', icon='close', on_click=lambda: dialog.submit(False))
            return dialog

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
      
       
