import logging
from nicegui import ui
from app.state import State
from app.customization import Customization
from app.app_storage import AppStorage
from app.messages import Messages
from app.theme import *
from app.game_manager import GameManager
from app.preview import create_iframe_card
import asyncio

class GUI:
    """
    Manages the Graphical User Interface for the scoreboard.
    It acts as the presentation layer.
    """
    PREVIEW_ENABLED_ICON = 'image_not_supported'
    PREVIEW_DISABLED_ICON = 'preview'

    def __init__(self, tabs=None, conf=None, backend=None):
        self.logger = logging.getLogger("GUI")
        self.undo = False
        self.simple = False
        self.current_set = 1
        self.visible = True
        self.initialized = False
        self.tabs = tabs
        self.conf = conf
        self.backend = backend
        self.game_manager = GameManager(self.conf, self.backend)
        self.visible = backend.is_visible()
        self.set_selector = None
        self.page_height = None
        self.page_width = None
        self.PADDINGS = GAME_BUTTON_PADDING_NORMAL
        self.TEXTSIZE = GAME_BUTTON_TEXT_NORMAL
        self.hide_timer = None
        self.long_press_timer = None
        self.teamA_logo = None
        self.teamB_logo = None
        self.score_labels = []
        # Flag to control event processing gate
        self.click_gate_open = True
        self.preview_container = None
        self.preview_button = None
        self.preview_visible = self.conf.show_preview
        
        # --- Reusable Dialog for Custom Values ---
        self.dialog_team = None
        self.dialog_is_set = None
        with ui.dialog() as self.custom_value_dialog, ui.card():
            self.dialog_label = ui.label()
            self.dialog_input = ui.number(
                step=1,
                format='%.0f'
            ).classes('w-full').mark('value-input')
            with ui.row():
                ui.button('OK', on_click=self._handle_custom_value_submit).mark('value-input-ok-button')
                ui.button('Cancel', on_click=self.custom_value_dialog.close).mark('value-input-cancel-button')


    def set_customization_model(self, model):
        """Directly sets the customization model from an external source."""
        self.logger.debug("Setting customization model directly.")
        self.current_customize_state.set_model(model)

    def set_page_size(self, width, height):
        """Adjusts UI element sizes based on page dimensions."""
        self.page_height = height
        self.page_width = width
        self.logger.debug('Set page size to: %sx%s',
                         self.page_height, self.page_width)

        is_landscape = self.page_width >= self.page_height
        dimension = self.page_width if is_landscape else self.page_height

        if dimension > 850:
            self.switch_padding_and_textsize(
                GAME_BUTTON_PADDING_BIG, GAME_BUTTON_TEXT_BIG)
        elif dimension > 745 or (not is_landscape and dimension > 800):
            self.switch_padding_and_textsize(
                GAME_BUTTON_PADDING_NORMAL, GAME_BUTTON_TEXT_NORMAL)
        else:
            self.switch_padding_and_textsize(
                GAME_BUTTON_PADDING_SMALL, GAME_BUTTON_TEXT_NORMAL)

    def switch_padding_and_textsize(self, padding, textsize):
        """Helper to switch padding and text size at once."""
        self.switch_padding(padding)
        self.switch_textsize(textsize)

    def switch_padding(self, padding):
        """Switches the padding for the team buttons."""
        if self.initialized:
            self.teamAButton.classes(remove=self.PADDINGS)
            self.teamBButton.classes(remove=self.PADDINGS)
        self.PADDINGS = padding
        self.logger.info("Change paddings to %s", padding)
        if self.initialized:
            self.teamAButton.classes(add=self.PADDINGS)
            self.teamBButton.classes(add=self.PADDINGS)

    def switch_textsize(self, textsize):
        """Switches the text size for the team buttons."""
        if self.initialized:
            self.teamAButton.classes(remove=self.TEXTSIZE)
            self.teamBButton.classes(remove=self.TEXTSIZE)
        self.TEXTSIZE = textsize
        self.logger.info("Change textsize to %s", textsize)
        if self.initialized:
            self.teamAButton.classes(add=self.TEXTSIZE)
            self.teamBButton.classes(add=self.TEXTSIZE)

    def _handle_custom_value_submit(self):
        """Submits the value from the reusable dialog."""
        self.custom_value_dialog.submit(self.dialog_input.value)

    async def show_custom_value_dialog(self, team: int, is_set_button: bool, initial_value: int, max_value: int):
        """Opens a reusable dialog to set a custom value for points or sets."""
        title = Messages.get(Messages.SET_CUSTOM_SET_VALUE) if is_set_button else Messages.get(Messages.SET_CUSTOM_GAME_VALUE)
        
        # Store context for the submit handler
        self.dialog_team = team
        self.dialog_is_set = is_set_button

        # Update dialog elements with current context
        self.dialog_label.set_text(title)
        self.dialog_input.label = Messages.get(Messages.VALUE)
        self.dialog_input.value = initial_value
        self.dialog_input.min = 0
        self.dialog_input.max = max_value
        
        result = await self.custom_value_dialog
        
        if result is not None:
            value = int(result)
            # Use the stored context to apply the value
            if self.dialog_is_set:
                self.set_sets_value(self.dialog_team, value)
            else:
                self.set_game_value(self.dialog_team, value)
        
        self.open_click_gate()

    def open_click_gate(self):
        """Opens the gate to allow new click events."""
        self.click_gate_open = True
        
    def handle_button_press(self, team: int, is_set_button: bool):
        """Starts a timer on mousedown/touchstart to detect a long press."""
        if not self.click_gate_open:
            return
        self.click_gate_open = False  # Close the gate immediately

        if is_set_button:
            button = self.teamASet if team == 1 else self.teamBSet
            initial_value = int(button.text)
            max_value = self.sets_limit
        else:
            button = self.teamAButton if team == 1 else self.teamBButton
            initial_value = int(button.text)
            max_value = self.get_game_limit(self.current_set)

        async def long_press_callback():
            self.long_press_timer = None
            await self.show_custom_value_dialog(team, is_set_button, initial_value, max_value)

        self.long_press_timer = ui.timer(0.5, long_press_callback, once=True)

    def handle_button_release(self, team: int, is_set_button: bool):
        """Cancels the timer on mouseup/touchend and handles the click action."""
        if self.long_press_timer is not None:
            self.long_press_timer.cancel()
            self.long_press_timer = None
            if is_set_button:
                self.add_set(team)
            else:
                self.add_game(team)
        
        # Re-open the gate after a short delay to ignore ghost clicks
        ui.timer(0.2, self.open_click_gate, once=True)

    def handle_press_cancel(self):
        """Cancels the long press timer if the touch moves."""
        if self.long_press_timer is not None:
            self.long_press_timer.cancel()
            self.long_press_timer = None
        self.open_click_gate() # Re-open gate immediately if press is cancelled

    async def toggle_preview(self):
        self.preview_visible = not self.preview_visible
        AppStorage.save(AppStorage.Category.SHOW_PREVIEW, self.preview_visible, oid=self.conf.oid)
        if self.preview_button is not None:
            icon = GUI.PREVIEW_ENABLED_ICON if self.preview_visible else GUI.PREVIEW_DISABLED_ICON
            self.preview_button.set_icon(icon)

        if self.preview_visible:
            if self.preview_container is not None:
                with self.preview_container:
                    await create_iframe_card(self.conf.output, self.current_customize_state.get_h_pos(), self.current_customize_state.get_v_pos(), self.current_customize_state.get_width(), self.current_customize_state.get_height())
        elif self.preview_container is not None:
            self.preview_container.clear()

    def _create_team_panel(self, team_id, button_color, timeout_light_color, serve_vlight_color):
        """Creates the UI panel for a single team."""
        with ui.card():
            button = ui.button('00', color=button_color).mark(f'team-{team_id}-score')
            button.on('mousedown', lambda: self.handle_button_press(
                team_id, is_set_button=False))
            button.on('touchstart', lambda: self.handle_button_press(
                team_id, is_set_button=False), [])
            button.on('mouseup', lambda: self.handle_button_release(
                team_id, is_set_button=False))
            button.on('touchend', lambda: self.handle_button_release(
                team_id, is_set_button=False))
            button.on('touchmove', self.handle_press_cancel)
            button.classes(self.PADDINGS + GAME_BUTTON_CLASSES + self.TEXTSIZE)

            with ui.row().classes('text-4xl w-full'):
                ui.button(icon='timer', color=timeout_light_color,
                          on_click=lambda: self.add_timeout(team_id)).props('outline round').mark(f'team-{team_id}-timeout').classes('shadow-lg')
                timeouts = ui.column().mark(f'team-{team_id}-timeouts-display')
                ui.space()
                serve_icon = ui.icon(
                    name='sports_volleyball', color=serve_vlight_color).mark(f'team-{team_id}-serve')
                serve_icon.on('click', lambda: self.change_serve(team_id))
        return button, timeouts, serve_icon

    async def _create_center_panel(self):
        """Creates the central control panel with set scores and pagination."""
        with ui.column().classes('h-full justify-end'):
            with ui.row().classes('w-full justify-center'):
                self.teamASet = ui.button('0', color='gray-700').mark('team-1-sets')
                self.teamASet.on('mousedown', lambda: self.handle_button_press(
                    1, is_set_button=True))
                self.teamASet.on('touchstart', lambda: self.handle_button_press(
                    1, is_set_button=True), [])
                self.teamASet.on('mouseup', lambda: self.handle_button_release(
                    1, is_set_button=True))
                self.teamASet.on('touchend', lambda: self.handle_button_release(
                    1, is_set_button=True))
                self.teamASet.on('touchmove', self.handle_press_cancel)
                self.teamASet.classes('text-white text-2xl')

                with ui.row():
                    self.scores = ui.grid(columns=2, rows=max(self.current_set, self.conf.sets)+1).classes('justify-center')
                    with self.scores:
                        logo1_src = self.current_customize_state.get_team_logo(1)
                        logo2_src = self.current_customize_state.get_team_logo(2)
                        self.teamA_logo = ui.image(source=logo1_src).classes('w-6 h-6 m-auto').mark('team-1-logo')
                        self.teamB_logo = ui.image(source=logo2_src).classes('w-6 h-6 m-auto').mark('team-2-logo')

                self.teamBSet = ui.button('0', color='gray-700').mark('team-2-sets')
                self.teamBSet.on('mousedown', lambda: self.handle_button_press(
                    2, is_set_button=True))
                self.teamBSet.on('touchstart', lambda: self.handle_button_press(
                    2, is_set_button=True), [])
                self.teamBSet.on('mouseup', lambda: self.handle_button_release(
                    2, is_set_button=True))
                self.teamBSet.on('touchend', lambda: self.handle_button_release(
                    2, is_set_button=True))
                self.teamBSet.on('touchmove', self.handle_press_cancel)
                self.teamBSet.classes('text-white text-2xl')

            self.set_selector = ui.pagination(1, self.sets_limit, direction_links=True, on_change=lambda e: self.switch_to_set(
                e.value)).props('color=grey active-color=teal').classes('w-full justify-center').mark('set-selector')
            ui.space()
            if self.conf.show_preview and self.conf.output is not None:
                self.preview_container = ui.column()
                if self.preview_visible:
                    with self.preview_container:
                        await create_iframe_card(self.conf.output, self.current_customize_state.get_h_pos(), self.current_customize_state.get_v_pos(), self.current_customize_state.get_width(), self.current_customize_state.get_height())

    def _create_control_buttons(self):
        """Creates the main control buttons (visibility, simple mode, undo, etc.)."""
        with ui.row().classes("w-full justify-around"):
            self.visibility_button = ui.button(icon='visibility', color=VISIBLE_ON_COLOR,
                                               on_click=self.switch_visibility).props('round').mark('visibility-button').classes('text-white')
            self.simple_button = ui.button(icon='grid_on', color=FULL_SCOREBOARD_COLOR,
                                           on_click=self.switch_simple_mode).props('round').mark('simple-mode-button').classes('text-white')

            self.undo_button = ui.button(icon='undo', color=UNDO_COLOR, on_click=lambda: self.switch_undo(
                False)).props('round').mark('undo-button').classes('text-white')
            if not self.conf.disable_overview and self.conf.output is not None:
                icon = GUI.PREVIEW_ENABLED_ICON if self.preview_visible else GUI.PREVIEW_DISABLED_ICON
                self.preview_button = ui.button(icon=icon, on_click=self.toggle_preview).props(
                        'round').mark('preview-button').classes('text-gray')
            ui.space()
            
            ui.button(icon='keyboard_arrow_right', color='stone-500', on_click=lambda: self.tabs.set_value(
                Customization.CONFIG_TAB)).props('round').mark('config-tab-button').classes('text-white')

    async def init(self, force=True, custom_points_limit=None, custom_points_limit_last_set=None, custom_sets_limit=None):
        if self.initialized and not force:
            return

        self.game_manager = GameManager(self.conf, self.backend)

        self.current_customize_state = Customization(
            self.backend.get_current_customization())
        self.logger.info('Initialize gui')

        self.points_limit = custom_points_limit if custom_points_limit is not None else self.conf.points
        self.points_limit_last_set = custom_points_limit_last_set if custom_points_limit_last_set is not None else self.conf.points_last_set
        self.sets_limit = custom_sets_limit if custom_sets_limit is not None else self.conf.sets

        self.logger.info('Set points: %s', self.points_limit)
        self.logger.info('Set points last set: %s',
                         self.points_limit_last_set)
        self.logger.info('Sets to win: %s', self.sets_limit)

        with ui.row().classes('w-full'):
            self.teamAButton, self.timeoutsA, self.serveA = self._create_team_panel(
                1, BLUE_BUTTON_COLOR, TACOLOR_LIGHT, TACOLOR_VLIGHT)
            ui.space()
            await self._create_center_panel()
            ui.space()
            self.teamBButton, self.timeoutsB, self.serveB = self._create_team_panel(
                2, RED_BUTTON_COLOR, TBCOLOR_LIGHT, TBCOLOR_VLIGHT)

        self._create_control_buttons()

        self.update_ui(False)
        self.initialized = True
        self.logger.info('Initialized gui')

    def compute_current_set(self, current_state):
        t1sets = current_state.get_sets(1)
        t2sets = current_state.get_sets(2)
        current_sets = t1sets + t2sets
        if not self.game_manager.match_finished():
            current_sets += 1
        return current_sets

    def update_ui_logos(self):
        """Updates the team logos without recreating the elements."""
        logo1_src = self.current_customize_state.get_team_logo(1)
        logo2_src = self.current_customize_state.get_team_logo(2)
        self.teamA_logo.set_source(logo1_src)
        self.teamB_logo.set_source(logo2_src)

    def update_ui(self, load_from_backend=False):
        self.logger.debug('Updating UI...')
        if load_from_backend:
            self.logger.info('loading data from backend')
            self.game_manager = GameManager(self.conf, self.backend)
            self.current_customize_state.set_model(
                self.backend.get_current_customization())
            self.visible = self.backend.is_visible()
            self.update_ui_logos()

        update_state = self.game_manager.get_current_state()
 
        self.current_set = self.compute_current_set(update_state)

        self.update_ui_serve(update_state)
        self.update_ui_sets(update_state)
        self.update_ui_games(update_state)
        self.update_ui_timeouts(update_state)
        self.update_ui_current_set(self.current_set)
        self.update_ui_visible(self.visible)
        clientSimple = AppStorage.load(
            AppStorage.Category.SIMPLE_MODE, oid=self.conf.oid)
        if clientSimple is not None:
            self.switch_simple_mode(clientSimple)

    def update_ui_games(self, update_state):
        """Updates the game scores on the UI."""
        for i in range(1, self.sets_limit + 1):
            teamA_game_int = update_state.get_game(1, i)
            teamB_game_int = update_state.get_game(2, i)
            if i == self.current_set:
                self.logger.debug(f'setting games {teamA_game_int:02d} {teamB_game_int:02d} on current set {self.current_set:01d}')
                self.teamAButton.set_text(f'{teamA_game_int:02d}')
                self.teamBButton.set_text(f'{teamB_game_int:02d}')
        self.update_ui_games_table(update_state)

    def update_ui_games_table(self, update_state):
        # Clear only the score labels, not the logos
        for label in self.score_labels:
            label.delete()
        self.score_labels.clear()

        with self.scores:
            lastWithoutZeroZero = 1
            match_finished = self.game_manager.match_finished()
            for i in range(1, self.sets_limit + 1):
                teamA_game_int = update_state.get_game(1, i)
                teamB_game_int = update_state.get_game(2, i)
                if teamA_game_int + teamB_game_int > 0:
                    lastWithoutZeroZero = i

            for i in range(1, self.sets_limit + 1):
                teamA_game_int = update_state.get_game(1, i)
                teamB_game_int = update_state.get_game(2, i)
                if i > 1 and i > lastWithoutZeroZero:
                    break
                if i == self.current_set and i < self.sets_limit and not match_finished:
                    break

                # Create and store references to the labels
                label1 = ui.label(f'{teamA_game_int:02d}').classes('p-0').mark(f'team-1-set-{i}-score')
                label2 = ui.label(f'{teamB_game_int:02d}').classes('p-0').mark(f'team-2-set-{i}-score')
                self.score_labels.extend([label1, label2])

                if teamA_game_int > teamB_game_int:
                    label1.classes('text-bold')
                elif teamA_game_int < teamB_game_int:
                    label2.classes('text-bold')

    def update_ui_timeouts(self, update_state):
        self.change_ui_timeout(1, update_state.get_timeout(1))
        self.change_ui_timeout(2, update_state.get_timeout(2))

    def update_ui_serve(self, update_state):
        """
        Updates the serve icons based on the current state.
        """
        current_serve = update_state.get_current_serve()
        self.serveA.props(
            f'color={TACOLOR_HIGH if current_serve == State.SERVE_1 else TACOLOR_VLIGHT}')
        self.serveB.props(
            f'color={TBCOLOR_HIGH if current_serve == State.SERVE_2 else TBCOLOR_VLIGHT}')

    def update_ui_sets(self, update_state):
        t1sets = update_state.get_sets(1)
        t2sets = update_state.get_sets(2)
        self.teamASet.set_text(str(t1sets))
        self.teamBSet.set_text(str(t2sets))

    def update_ui_current_set(self, set_number):
        self.set_selector.set_value(set_number)

    def update_ui_visible(self, enabled):
        icon = 'visibility' if enabled else 'visibility_off'
        color = VISIBLE_ON_COLOR if enabled else VISIBLE_OFF_COLOR
        self.visibility_button.set_icon(icon)
        self.visibility_button.props(f'color={color}')

    def send_state(self):
        """Sends the current state to the backend."""
        self.game_manager.save(self.simple, self.current_set)

    async def reset(self):
        """Resets the game state, saves it, and updates the UI."""
        self.logger.debug('Reset called')
        self.game_manager.reset()
        self.update_ui(load_from_backend=True)


    async def refresh(self):
        """Reloads the game state from the backend and updates the UI."""
        self.logger.debug('Refresh called, reloading state from backend.')
        self.update_ui(load_from_backend=True)
        

    def change_serve(self, team, force=False):
        self.game_manager.change_serve(team, force)
        self.update_ui_serve(self.game_manager.get_current_state())
        self.send_state()

    def add_timeout(self, team):
        self.game_manager.add_timeout(team, self.undo)
        if self.undo:
            self.switch_undo(True)
        if self.is_auto_simple_mode_timeout_enabled():
            self.logger.debug('Switch simple mode off due to auto_simple_mode_timeout being enabled')
            self.switch_simple_mode(False)
        self.update_ui_timeouts(self.game_manager.get_current_state())
        self.send_state()

    def change_ui_timeout(self, team, value):
        color = TACOLOR_MEDIUM if team == 1 else TBCOLOR_MEDIUM
        container = self.timeoutsA if team == 1 else self.timeoutsB
        container.clear()
        with container:
            for n in range(value):
                ui.icon(name='radio_button_unchecked',
                          color=color, size='12px').mark(f'timeout-{team}-number-{n}')

    def set_game_value(self, team: int, value: int):
        """Directly sets the game score for a team."""
        self.game_manager.set_game_value(team, value, self.current_set)
        
        set_won = self.game_manager.check_set_won(
            team, self.current_set, self.points_limit, self.points_limit_last_set, self.sets_limit
        )

        # Always update the main score button right after setting the value.
        # This ensures the winning score is displayed.
        current_state = self.game_manager.get_current_state()
        self.teamAButton.set_text(f'{current_state.get_game(1, self.current_set):02d}')
        self.teamBButton.set_text(f'{current_state.get_game(2, self.current_set):02d}')

        if set_won:
            self.update_ui_sets(current_state)
            self.update_ui_timeouts(current_state)
            if not self.game_manager.match_finished():
                self.switch_to_set(self.compute_current_set(current_state))
        
        # Update the detailed score table regardless.
        self.update_ui_games_table(current_state)
        self.send_state()


    def set_sets_value(self, team: int, value: int):
        """Directly sets the sets won for a team."""
        self.game_manager.set_sets_value(team, value)
        self.update_ui_sets(self.game_manager.get_current_state())
        self.switch_to_set(
            self.compute_current_set(self.game_manager.get_current_state()))
        self.send_state()

    def add_game(self, team):
        if self.block_additional_points():
            ui.notify(Messages.get(Messages.MATCH_FINISHED))
            return

        set_won = self.game_manager.add_game(
            team, self.current_set, self.points_limit, self.points_limit_last_set, self.sets_limit, self.undo)

        # Explicitly update the main score buttons with the score of the set that was just played.
        current_state = self.game_manager.get_current_state()
        self.teamAButton.set_text(f'{current_state.get_game(1, self.current_set):02d}')
        self.teamBButton.set_text(f'{current_state.get_game(2, self.current_set):02d}')

        self.update_ui_serve(current_state)

        if self.undo:
            self.switch_undo(True)

        if self.is_auto_hide_enabled():
            if self.hide_timer:
                self.hide_timer.cancel()
            self.logger.debug('Auto hide enabled, sitching visibility on')
            self.switch_visibility(True)

        if set_won:
            self.update_ui_sets(current_state)
            self.update_ui_timeouts(current_state)
            if not self.game_manager.match_finished():
                self.switch_to_set(self.compute_current_set(current_state))
            if self.is_auto_simple_mode_enabled():
                self.logger.debug('Switch simple mode off due to auto_simple_mode being enabled')
                self.switch_simple_mode(False)
        else:
            if self.is_auto_hide_enabled():
                hide_timeout = self.get_hide_timeout()
                self.logger.debug(f'Auto hide enabled, enabling timer to hide after %s seconds', hide_timeout)
                self.hide_timer = ui.timer(
                    hide_timeout, lambda: self.switch_visibility(False), once=True)
            if self.is_auto_simple_mode_enabled():
                self.logger.debug('Switch simple mode on due to auto_simple_mode being enabled')
                self.switch_simple_mode(True)
        
        self.update_ui_games_table(self.game_manager.get_current_state())
        self.send_state()

    def get_game_limit(self, set_number):
        return self.points_limit_last_set if set_number == self.sets_limit else self.points_limit

    def add_set(self, team):
        if self.block_additional_points():
            ui.notify(Messages.get(Messages.MATCH_FINISHED))
            return

        self.game_manager.add_set(team, self.undo)

        if self.undo:
            self.switch_undo(True)

        self.update_ui_sets(self.game_manager.get_current_state())
        self.switch_to_set(
            self.compute_current_set(self.game_manager.get_current_state()))
        self.send_state()

    def block_additional_points(self):
        return not self.undo and self.game_manager.match_finished()

    def is_auto_hide_enabled(self):
        stored = AppStorage.load(AppStorage.Category.AUTOHIDE_ENABLED, oid=self.conf.oid)
        if stored is not None:
            return stored
        return self.conf.auto_hide

    def get_hide_timeout(self):
        stored = AppStorage.load(AppStorage.Category.AUTOHIDE_SECONDS, oid=self.conf.oid)
        if stored is not None:
            return int(stored)
        return self.conf.hide_timeout

    def is_auto_simple_mode_enabled(self):
        stored = AppStorage.load(AppStorage.Category.SIMPLIFY_OPTION_ENABLED, oid=self.conf.oid)
        if stored is not None:
            return stored
        return self.conf.auto_simple_mode

    def is_auto_simple_mode_timeout_enabled(self):
        stored = AppStorage.load(AppStorage.Category.SIMPLIFY_ON_TIMEOUT_ENABLED, oid=self.conf.oid)
        if stored is not None:
            return stored
        return self.conf.auto_simple_mode_timeout

    def switch_to_set(self, set_number):
        if self.current_set != set_number:
            self.current_set = set_number
            self.update_ui_current_set(self.current_set)
            self.update_ui_games(self.game_manager.get_current_state())

    def switch_visibility(self, force_value=None):
        update = False
        visible_backup = self.visible
        if self.visible and force_value is not True:
            self.visible = False
            update = True
        elif not self.visible and force_value is not False:
            self.visible = True
            update = True
        self.logger.debug('Switch visibility to %s. Current %s. Update: %s', self.visible, visible_backup, update)
        if update:
            self.update_ui_visible(self.visible)
            self.backend.change_overlay_visibility(self.visible)

    def switch_simple_mode(self, force_value=None):
        if self.simple and force_value is not True:
            self.simple = False
            self.simple_button.set_icon('grid_on')
            self.simple_button.props(f'color={FULL_SCOREBOARD_COLOR}')
        elif not self.simple and force_value is not False:
            self.simple = True
            self.simple_button.set_icon('window')
            self.simple_button.props(f'color={SIMPLE_SCOREBOARD_COLOR}')
            self.backend.reduce_games_to_one()

        if force_value is None:
            AppStorage.save(AppStorage.Category.SIMPLE_MODE,
                              self.simple, oid=self.conf.oid)
        self.send_state()

    def switch_undo(self, reset=False):
        if self.undo:
            self.logger.info('Undo switched off')
            self.undo = False
            self.undo_button.set_icon('undo')
            self.undo_button.props(f'color={UNDO_COLOR}')
        elif not reset:
            self.logger.info('Undo enabled')
            self.undo = True
            self.undo_button.set_icon('redo')
            self.undo_button.props(f'color={DO_COLOR}')
