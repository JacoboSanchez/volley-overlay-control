import asyncio
import logging
from nicegui import ui, app
from app.conf import Conf
from app.backend import Backend
from app.state import State
from app.customization import Customization
from app.authentication import PasswordAuthenticator
from app.messages import Messages
from app.options_dialog import OptionsDialog
from app.app_storage import AppStorage


class CustomizationPage:
    logger = logging.getLogger("Customization Page")

    def __init__(self, tabs=None, configuration=None, backend=None, gui=None, options=None):
        self.tabs = tabs
        if configuration is not None:
            self.configuration = configuration
        else:
            self.configuration = Conf()
        if backend is not None:
            self.backend = backend
        else:
            self.backend = Backend(self.configuration)
        self.gui = gui
        self.customization = Customization(
            self.backend.get_current_customization())
        self.options_dialog = options
        self.container = None  # Initialize container attribute

        with ui.dialog().props('persistent') as self.dialog_reset, ui.card():
            ui.label(Messages.get(Messages.ASK_RESET))
            with ui.row():
                ui.button(color='green-500', icon='done',
                          on_click=lambda: self.dialog_reset.submit(True)).mark('confirm-reset-button')
                ui.button(color='red-500', icon='close',
                          on_click=lambda: self.dialog_reset.submit(False)).mark('cancel-reset-button')

        with ui.dialog().props('persistent') as self.dialog_reload, ui.card():
            ui.label(Messages.get(Messages.ASK_RELOAD))
            with ui.row():
                ui.button(color='green-500', icon='done',
                          on_click=lambda: self.dialog_reload.submit(True)).mark('confirm-refresh-button')
                ui.button(color='red-500', icon='close',
                          on_click=lambda: self.dialog_reload.submit(False)).mark('cancel-refresh-button')

        with ui.dialog().props('persistent') as self.logout_dialog, ui.card():
            ui.label(Messages.get(Messages.ASK_LOGOUT))
            with ui.row():
                ui.button(color='green-500', icon='done',
                            on_click=lambda: self.logout_dialog.submit(True)).mark('confirm-logout-button')
                ui.button(color='red-500', icon='close',
                            on_click=lambda: self.logout_dialog.submit(False)).mark('cancel-logout-button')



    def update_team_selection(self, team, logo, tname, color, textColor, selector):
        fallback_name = CustomizationPage.get_fallback_team_name(team)
        team_name = tname if tname is not None else fallback_name
        teamValues = Customization.get_predefined_teams().get(team_name, None)
        if teamValues is None:
            teamValues = Customization.get_predefined_teams(
            )[CustomizationPage.get_fallback_team_name(team)]
        lockedColors = self.configuration.lock_teamA_colors if team == 1 else self.configuration.lock_teamB_colors
        lockedIcon = self.configuration.lock_teamA_icons if team == 1 else self.configuration.lock_teamB_icons
        if not lockedIcon:
            logo.set_source(teamValues[Customization.TEAM_VALUES_ICON])
        if not lockedColors:
            color.classes(
                replace=f'!bg-[{teamValues[Customization.TEAM_VALUES_COLOR]}]')
            textColor.classes(
                replace=f'!bg-[{teamValues[Customization.TEAM_VALUES_TEXT_COLOR]}]')
            selector.classes(
                replace=f'!bg-[{teamValues[Customization.TEAM_VALUES_COLOR]}] w-[300px]')
            selector.classes(
                replace=f'!fg-[{teamValues[Customization.TEAM_VALUES_TEXT_COLOR]}] w-[300px]')
        self.customization.set_team_name(team, tname)
        if not lockedIcon:
            self.customization.set_team_logo(
                team, teamValues[Customization.TEAM_VALUES_ICON])
        if not lockedColors:
            self.customization.set_team_color(
                team, teamValues[Customization.TEAM_VALUES_COLOR])
            self.customization.set_team_text_color(
                team, teamValues[Customization.TEAM_VALUES_TEXT_COLOR])

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
            # Re-initialize the UI with the new theme data without fetching from the backend again
            self.init(self.container, force_reset=False)

    async def show_theme_dialog(self):
        with ui.dialog().props('persistent') as dialog, ui.card():
            ui.label(Messages.get(Messages.THEME_TITLE)).classes('text-lg font-semibold')
            theme_list = self.customization.get_theme_names()
            if not theme_list:
                ui.label(Messages.get(Messages.NO_THEMES))
                ui.button(Messages.get(Messages.CLOSE), on_click=dialog.close).props('flat').classes('w-full mt-4')
            else:
                selection = ui.select(list(theme_list), label=Messages.get(
                    Messages.THEME)).classes('w-[300px]').props('outlined').mark('theme-selector')
                with ui.row().classes('w-full'):
                    ui.button(Messages.get(Messages.LOAD),
                            on_click=lambda: self.apply_and_refresh(selection.value, dialog)).props('flat').mark('load-theme-button')
                    ui.space()
                    ui.button(Messages.get(Messages.CLOSE),
                            on_click=dialog.close).props('flat').mark('close-theme-button')
        await dialog

    def _setup_container(self, configuration_container=None):
        """Prepares the UI container, clearing it if necessary."""
        if configuration_container is not None:
            self.container = configuration_container
        if self.container is not None:
            self.container.clear()
            return True
        else:
            logging.warning('No container for customization...')
            return False

    def _prepare_team_names(self):
        """Prepares and returns the list of team names for the selectors."""
        team_names = list(Customization.get_predefined_teams())
        if self.configuration.orderedTeams:
            team_names.sort()

        for team_id in [1, 2]:
            team_name = self.customization.get_team_name(team_id)
            if team_name not in team_names:
                team_names.append(team_name)
        return team_names

    def _create_scoreboard_options_card(self):
        """Creates the scoreboard options card (logos, gradient, colors)."""
        with ui.card():
            with ui.row():
                ui.switch(Messages.get(Messages.LOGOS), value=self.customization.is_show_logos(),
                          on_change=lambda e: self.customization.set_show_logos(e.value)).mark('logo-switch')
                ui.switch(Messages.get(Messages.GRADIENT), value=self.customization.is_glossy(),
                          on_change=lambda e: self.customization.set_glossy(e.value)).mark('gradient-switch')

            with ui.row():
                self.create_choose_color(Messages.get(Messages.SET), True)
                self.create_choose_color(Messages.get(Messages.GAME), False)

    def _create_scoreboard_geometry_card(self):
        """Creates the geometry and links configuration card."""
        with ui.card():
            with ui.row().classes('place-content-center align-middle'):
                ui.number(label=Messages.get(Messages.HEIGHT), value=self.customization.get_height(), format='%.1f',
                          min=0, max=100, on_change=lambda e: self.customization.set_height(f'{e.value}')).mark('height-input')
                ui.space()
                ui.number(label=Messages.get(Messages.WIDTH), value=self.customization.get_width(), format='%.1f',
                          min=0, max=100, on_change=lambda e: self.customization.set_width(f'{e.value}')).mark('width-input')
                ui.space()
                ui.number(label=Messages.get(Messages.HPOS), value=self.customization.get_h_pos(),
                          format='%.1f', min=-50, max=50, on_change=lambda e: self.customization.set_h_pos(f'{e.value}')).mark('hpos-input')
                ui.space()
                ui.number(label=Messages.get(Messages.VPOS), value=self.customization.get_v_pos(),
                          format='%.1f', min=-50, max=50, on_change=lambda e: self.customization.set_v_pos(f'{e.value}')).mark('vpos-input')

            def reset_and_reload():
                """Clears stored OID and reloads the page."""
                AppStorage.save(AppStorage.Category.CONFIGURED_OID, None)
                AppStorage.save(AppStorage.Category.CONFIGURED_OUTPUT, None)
                ui.navigate.to('/')

            with ui.row().classes('items-center w-full'):
                if len(list(self.customization.get_theme_names())) > 0:
                    ui.button(icon='palette',
                              on_click=self.show_theme_dialog).props('flat').mark('theme-button')
                ui.button(icon='link', on_click=self.show_links_dialog).props('flat round dense color=primary') \
                    .tooltip(Messages.get(Messages.LINKS)).mark('links-button')
                ui.button(icon='tune', on_click=self.options_dialog.open).props(
                    'flat').classes('text-gray-500 -ml-2 mr-2').mark('options-button')
                # Only show the reset button if an OID is stored
                ui.space()
                if AppStorage.load(AppStorage.Category.CONFIGURED_OID, None) is not None:
                    ui.button(icon='logout', on_click=reset_and_reload) \
                        .props('flat round dense color=primary') \
                        .tooltip(Messages.get(Messages.RESET_LINKS)).mark('change-overlay-button')
                

    async def show_links_dialog(self):
        with ui.dialog() as dialog, ui.card():
            ui.label(Messages.get(Messages.LINKS)).classes('text-h6')
            control_link = f'https://app.overlays.uno/control/{self.configuration.oid}'
            with ui.row().classes('items-center w-full'):
                ui.link(Messages.get(Messages.CONTROL_LINK),
                          control_link, new_tab=True)
                ui.space()
                ui.button(icon='content_copy', on_click=lambda: ui.run_javascript(
                    f'navigator.clipboard.writeText("{control_link}")')).props('flat round dense').tooltip(Messages.get(Messages.COPY_TO_CLIPBOARD))
            if self.configuration.output and self.configuration.output.strip():
                overlay_link = self.configuration.output
                with ui.row().classes('items-center w-full'):
                    ui.link(Messages.get(Messages.OVERLAY_LINK),
                              overlay_link, new_tab=True)
                    ui.space()
                    ui.button(icon='content_copy', on_click=lambda: ui.run_javascript(
                        f'navigator.clipboard.writeText("{overlay_link}")')).props('flat round dense').tooltip(Messages.get(Messages.COPY_TO_CLIPBOARD))
                
                token = overlay_link.split('/')[-1]
                posx = self.customization.get_h_pos()
                posy = self.customization.get_v_pos()
                width = self.customization.get_width()
                height = self.customization.get_height()

                preview_link = f'./preview?output={token}&width={width}&height={height}&x={posx}&y={posy}'
                with ui.row().classes('items-center w-full'):
                    ui.link(Messages.get(Messages.PREVIEW_LINK),
                              preview_link, new_tab=True)
                    ui.space()
                    ui.button(icon='content_copy', on_click=lambda: ui.run_javascript(
                        f'navigator.clipboard.writeText(new URL("{preview_link}", window.location.href).href)')).props('flat round dense').tooltip(Messages.get(Messages.COPY_TO_CLIPBOARD))
            with ui.row().classes('w-full'):
                ui.space()
                ui.button(Messages.get(Messages.CLOSE),
                          on_click=dialog.close).props('flat')
        await dialog

    def _create_action_buttons(self):
        """Creates the bottom row of action buttons."""
        with ui.row().classes('w-full'):
            ui.button(icon='keyboard_arrow_left', color='stone-500',
                      on_click=self.switch_to_scoreboard).props('round').mark('scoreboard-tab-button').classes('text-white')
            ui.space()
            ui.button(icon='save', color='blue-500',
                      on_click=self.save).props('round').mark('save-button').classes('text-white')
            ui.button(icon='sync', color='emerald-600',
                      on_click=self.ask_refresh).props('round').mark('refresh-button').classes('text-white')
            ui.button(icon='recycling', color='orange-500',
                      on_click=self.ask_reset).props('round').mark('reset-button').classes('text-white')

            if AppStorage.load(AppStorage.Category.USERNAME, None) is not None:
                ui.button(icon='logout', color='red-700',
                          on_click=self.ask_logout).props('round').mark('logout-button').classes('text-white')

    def init(self, configuration_container=None, force_reset=False):
        """Initializes and builds the customization page."""
        if force_reset:
            self.customization = Customization(
                self.backend.get_current_customization())

        self.logger.info("Initializing")
        if not self._setup_container(configuration_container):
            return

        with self.container:
            team_names = self._prepare_team_names()
            with ui.row().classes('items-center w-full'):
                with ui.grid(columns=1):
                    self.create_team_card(1, team_names)
                    self._create_scoreboard_options_card()
                ui.space()
                with ui.grid(columns=1):
                    self.create_team_card(2, team_names)
                    self._create_scoreboard_geometry_card()
            self._create_action_buttons()

        self.logger.info("Initialized customization page")

    def create_team_card(self, team, teamNames):
        self.customization.set_team_logo(
            team, self.customization.get_team_logo(team))
        with ui.card():
            with ui.row().classes('w-full'):
                selector = ui.select(teamNames,
                                     new_value_mode='add-unique',
                                     value=self.customization.get_team_name(
                                         team),
                                     key_generator=lambda k: k,
                                     on_change=lambda e: self.update_team_selection(team, team_logo, e.value, team_color, team_text_color, selector)
                                     ).classes('w-[300px]').props(f'outlined behavior=dialog label={CustomizationPage.get_fallback_team_name(team)}').mark(f'team-{team}-name-selector')
            with ui.row():
                team_logo = ui.image(self.customization.get_team_logo(team)).classes(
                    'w-9 h-9 m-auto')
                icon_lock_value = self.configuration.lock_teamA_icons if team == 1 else self.configuration.lock_teamB_icons
                icons_switch = ui.switch(on_change=lambda e: self.changed_icon_lock(
                    team, icons_switch, e.value), value=icon_lock_value).props('icon=no_encryption' if not icon_lock_value else 'icon=lock').mark(f'team-{team}-icon-lock')
                ui.space()
                team_color = ui.button().classes('w-8 h-8 m-auto')
                team_text_color = ui.button().classes('w-5 h-5')
                with team_color:
                    team_color_picker = ui.color_picker(on_pick=lambda e: self.update_team_model_color(
                        team, e.color, team_color, False))
                team_color_picker.q_color.props(
                    'default-view=palette no-header')
                with team_text_color:
                    team_text_color_picker = ui.color_picker(on_pick=lambda e: self.update_team_model_color(
                        team, e.color, team_text_color, True))
                team_text_color_picker.q_color.props(
                    'default-view=palette no-header')
                self.update_team_model_color(
                    team, self.customization.get_team_color(team), team_color, False)
                self.update_team_model_color(
                    team, self.customization.get_team_text_color(team), team_text_color, True)
                color_lock_value = self.configuration.lock_teamA_colors if team == 1 else self.configuration.lock_teamB_colors
                colors_switch = ui.switch(on_change=lambda e: self.changed_color_lock(
                    team, colors_switch, e.value), value=color_lock_value).props('icon=no_encryption' if not color_lock_value else 'icon=lock').mark(f'team-{team}-color-lock')

    def changed_icon_lock(self, team, switch_lock, value):
        if team == 1:
            AppStorage.save(AppStorage.Category.LOCK_TEAM_A_ICONS, value, oid=self.configuration.oid)
        else:
            AppStorage.save(AppStorage.Category.LOCK_TEAM_B_ICONS, value, oid=self.configuration.oid)
        if value:
            switch_lock.props('icon=lock')
        else:
            switch_lock.props('icon=no_encryption')

    def changed_color_lock(self, team, switch_lock, value):
        if team == 1:
            AppStorage.save(AppStorage.Category.LOCK_TEAM_A_COLORS, value, oid=self.configuration.oid)
        else:
            AppStorage.save(AppStorage.Category.LOCK_TEAM_B_COLORS, value, oid=self.configuration.oid)
        if value:
            switch_lock.props('icon=lock')
        else:
            switch_lock.props('icon=no_encryption')

    def create_choose_color(self, name, forSet=False):
        ui.label(name)
        with ui.row():
            main_color = ui.button().classes('w-8 h-8 m-auto')
            main_text_color = ui.button().classes('w-5 h-5')
        with main_color:
            main_color_picker = ui.color_picker(on_pick=lambda e: self.update_model_color(
                forSet, e.color, main_color, False))
        main_color_picker.q_color.props('default-view=palette no-header')
        with main_text_color:
            main_text_color_picker = ui.color_picker(
                on_pick=lambda e: self.update_model_color(forSet, e.color, main_text_color, True))
        main_text_color_picker.q_color.props('default-view=palette no-header')
        self.update_model_color(forSet, self.customization.get_set_color(
        ) if forSet else self.customization.get_game_color(), main_color, False)
        self.update_model_color(forSet, self.customization.get_set_text_color(
        ) if forSet else self.customization.get_game_text_color(), main_text_color, True)

    async def reload_customization(self):
        notification = ui.notification(timeout=None, spinner=True)
        await asyncio.sleep(0.1)
        try:
            self.init(self.container, force_reset=True)
        finally:
            notification.dismiss()

    async def save(self):
        logging.info('save called')
        notification = ui.notification(Messages.get(Messages.SAVING), spinner=True, timeout=None)
        await asyncio.sleep(0.1)
        try:
            new_model = self.customization.get_model()
            logging.debug('saving json configuration')
            self.backend.save_json_customization(new_model)
            logging.debug('setting customization model to gui')
            self.gui.set_customization_model(new_model)
            logging.debug('updating ui logos')
            self.gui.update_ui_logos()
            self.gui.update_button_style()
            self.switch_to_scoreboard()
        finally:
            notification.dismiss()

    async def ask_logout(self):
        result = await self.logout_dialog
        if result:
            PasswordAuthenticator.logout()

    async def ask_refresh(self):
        """Asks for confirmation and refreshes the data."""
        logging.debug('ask refresh called')
        result = await self.dialog_reload
        if result:
            logging.debug('refresh called')
            notification = ui.notification(Messages.get(Messages.LOADING), spinner=True, timeout=None)
            await asyncio.sleep(0.1)
            try:
                self.clear_local_cached_data_for_oid()
                await self.gui.refresh()
                self.init(self.container, force_reset=True)
            finally:
                notification.dismiss()
        else:
            logging.debug('refresh cancelled')


    async def ask_reset(self):
        """Asks for confirmation and resets the scoreboard."""
        logging.info('Ask reset called')
        result = await self.dialog_reset
        if result:
            notification = ui.notification(Messages.get(Messages.LOADING), spinner=True, timeout=None)
            logging.debug('reset confirmed')
            self.clear_local_cached_data_for_oid()
            await self.gui.reset()
            await asyncio.sleep(0.1)
            self.init(self.container, force_reset=True)
            notification.dismiss()
            self.switch_to_scoreboard()
        else:
            logging.debug('reset cancelled')

    def switch_to_scoreboard(self):
        """Switches to the scoreboard tab."""
        self.tabs.set_value(Customization.SCOREBOARD_TAB)

    def clear_local_cached_data_for_oid(self):
        AppStorage.refresh_state(oid=self.configuration.oid)