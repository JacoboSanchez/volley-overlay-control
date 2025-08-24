import logging
from nicegui import ui
from state import State
from customization import Customization
from app_storage import AppStorage
from messages import Messages

# Constants for colors and styles
# Team A Colors
TACOLOR = 'blue'
TACOLOR_VLIGHT = 'blue-1'
TACOLOR_LIGHT = 'blue-2'
TACOLOR_MEDIUM = 'blue-3'
TACOLOR_HIGH = 'blue-4'

# Team B Colors
TBCOLOR = 'red'
TBCOLOR_VLIGHT = 'red-1'
TBCOLOR_LIGHT = 'red-2'
TBCOLOR_MEDIUM = 'red-3'
TBCOLOR_HIGH = 'red-4'

# Other UI Colors
DO_COLOR = 'indigo-700'
UNDO_COLOR = 'indigo-400'
VISIBLE_ON_COLOR = 'green-600'
VISIBLE_OFF_COLOR = 'green-800'
FULL_SCOREBOARD_COLOR = 'orange-500'
SIMPLE_SCOREBOARD_COLOR = 'orange-700'
RED_BUTTON_COLOR = 'red'
BLUE_BUTTON_COLOR = 'blue'

# Button Styles
GAME_BUTTON_PADDING_BIG = 'p-16'
GAME_BUTTON_PADDING_NORMAL = 'p-14'
GAME_BUTTON_PADDING_SMALL = 'p-11'
GAME_BUTTON_TEXT_NORMAL = 'text-5xl'
GAME_BUTTON_TEXT_BIG = 'text-6xl'
GAME_BUTTON_CLASSES = ' text-center shadow-lg rounded-lg text-white font-bold '


class GUI:
    """
    Manages the Graphical User Interface for the scoreboard.
    """

    def __init__(self, tabs=None, conf=None, backend=None):
        self.logger = logging.getLogger("GUI")
        self.undo = False
        self.simple = False
        self.holdUpdate = 0
        self.current_set = 1
        self.visible = True
        self.initialized = False
        self.tabs = tabs
        self.conf = conf
        self.backend = backend
        self.current_customize_state = Customization(
            backend.get_current_customization())
        self.main_state = State(backend.get_current_model())
        self.visible = backend.is_visible()
        self.set_selector = None
        self.page_height = None
        self.page_width = None
        self.PADDINGS = GAME_BUTTON_PADDING_NORMAL
        self.TEXTSIZE = GAME_BUTTON_TEXT_NORMAL
        self.hide_timer = None
        self.long_press_timer = None

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

    def set_main_state(self, state):
        self.main_state = State(state)

    def get_current_state(self):
        return self.main_state

    async def show_custom_value_dialog(self, team: int, is_set_button: bool, initial_value: int, max_value: int):
        """Opens a dialog to set a custom value for points or sets."""
        title = Messages.get(Messages.SET_CUSTOM_SET_VALUE) if is_set_button else Messages.get(Messages.SET_CUSTOM_GAME_VALUE)
        with ui.dialog() as dialog, ui.card():
            ui.label(title)
            value_input = ui.number(
                label=Messages.get(Messages.VALUE),
                value=initial_value, 
                min=0, 
                max=max_value, 
                step=1, 
                format='%.0f'
            ).classes('w-full')
            with ui.row():
                ui.button('OK', on_click=lambda: dialog.submit(value_input.value))
                ui.button('Cancel', on_click=dialog.close)
        
        result = await dialog
        if result is not None:
            value = int(result)
            if is_set_button:
                self.set_sets_value(team, value)
            else:
                self.set_game_value(team, value)

    def handle_button_press(self, team: int, is_set_button: bool):
        """Starts a timer on mousedown/touchstart to detect a long press."""
        # Determine the button and its limits to pass to the dialog
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

    def handle_press_cancel(self):
        """Cancels the long press timer if the touch moves."""
        if self.long_press_timer is not None:
            self.long_press_timer.cancel()
            self.long_press_timer = None

    def _create_team_panel(self, team_id, button_color, timeout_light_color, serve_vlight_color):
        """Creates the UI panel for a single team."""
        with ui.card():
            button = ui.button('00', color=button_color)
            # Add handlers for both mouse and touch events
            button.on('mousedown', lambda: self.handle_button_press(team_id, is_set_button=False))
            button.on('touchstart', lambda: self.handle_button_press(team_id, is_set_button=False), [])
            button.on('mouseup', lambda: self.handle_button_release(team_id, is_set_button=False))
            button.on('touchend', lambda: self.handle_button_release(team_id, is_set_button=False))
            button.on('touchmove', self.handle_press_cancel)
            button.classes(self.PADDINGS + GAME_BUTTON_CLASSES + self.TEXTSIZE)
            
            with ui.row().classes('text-4xl w-full'):
                ui.button(icon='timer', color=timeout_light_color,
                          on_click=lambda: self.add_timeout(team_id)).props('outline round').classes('shadow-lg')
                timeouts = ui.column()
                ui.space()
                serve_icon = ui.icon(
                    name='sports_volleyball', color=serve_vlight_color)
                serve_icon.on('click', lambda: self.change_serve(team_id))
        return button, timeouts, serve_icon

    def _create_center_panel(self):
        """Creates the central control panel with set scores and pagination."""
        with ui.column().classes('justify-center'):
            with ui.row().classes('w-full justify-center'):
                self.teamASet = ui.button('0', color='gray-700')
                # Add handlers for both mouse and touch events
                self.teamASet.on('mousedown', lambda: self.handle_button_press(1, is_set_button=True))
                self.teamASet.on('touchstart', lambda: self.handle_button_press(1, is_set_button=True), [])
                self.teamASet.on('mouseup', lambda: self.handle_button_release(1, is_set_button=True))
                self.teamASet.on('touchend', lambda: self.handle_button_release(1, is_set_button=True))
                self.teamASet.on('touchmove', self.handle_press_cancel)
                self.teamASet.classes('text-white text-2xl')

                with ui.row():
                    self.scores = ui.grid(columns=2).classes('justify-center')
                
                self.teamBSet = ui.button('0', color='gray-700')
                # Add handlers for both mouse and touch events
                self.teamBSet.on('mousedown', lambda: self.handle_button_press(2, is_set_button=True))
                self.teamBSet.on('touchstart', lambda: self.handle_button_press(2, is_set_button=True), [])
                self.teamBSet.on('mouseup', lambda: self.handle_button_release(2, is_set_button=True))
                self.teamBSet.on('touchend', lambda: self.handle_button_release(2, is_set_button=True))
                self.teamBSet.on('touchmove', self.handle_press_cancel)
                self.teamBSet.classes('text-white text-2xl')

            self.set_selector = ui.pagination(1, self.sets_limit, direction_links=True, on_change=lambda e: self.switch_to_set(
                e.value)).props('color=grey active-color=teal')

    def _create_control_buttons(self):
        """Creates the main control buttons (visibility, simple mode, undo, etc.)."""
        with ui.row().classes("w-full justify-right"):
            self.visibility_button = ui.button(icon='visibility', color=VISIBLE_ON_COLOR,
                                               on_click=self.switch_visibility).props('round').classes('text-white')
            self.simple_button = ui.button(icon='grid_on', color=FULL_SCOREBOARD_COLOR,
                                           on_click=self.switch_simple_mode).props('round').classes('text-white')
            self.undo_button = ui.button(icon='undo', color=UNDO_COLOR, on_click=lambda: self.switch_undo(False)).props('round').classes('text-white')
            ui.space()
            ui.button(icon='keyboard_arrow_right', color='stone-500', on_click=lambda: self.tabs.set_value(
                Customization.CONFIG_TAB)).props('round').classes('text-white')

    def init(self, force=True, custom_points_limit=None, custom_points_limit_last_set=None, custom_sets_limit=None):
        if self.initialized and not force:
            return

        self.logger.info('Initialize gui')

        # Set game parameters
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
            self._create_center_panel()
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
        if not self.match_finished(t1sets, t2sets):
            current_sets += 1
        return current_sets

    def match_finished(self, t1sets, t2sets):
        limit = self.sets_limit
        soft_limit = 2 if self.sets_limit == 3 else 3
        if (t1sets + t2sets < limit and t1sets < soft_limit and t2sets < soft_limit):
            return False
        self.logger.info('Match finished')
        return True

    def update_ui(self, load_from_backend=False):
        global visible
        self.logger.info('Updating UI...')
        if load_from_backend or self.conf.cache:
            self.logger.info('loading data from backend')
            self.current_customize_state.set_model(
                self.backend.get_current_customization())
            update_state = State(self.backend.get_current_model())
            visible = self.backend.is_visible()
        else:
            update_state = self.main_state

        current_set = self.compute_current_set(update_state)
        self.update_ui_serve(update_state)
        self.update_ui_sets(update_state)
        self.update_ui_games(update_state)
        self.update_ui_timeouts(update_state)
        self.update_ui_current_set(current_set)
        self.update_ui_visible(visible)
        clientSimple = AppStorage.load(
            AppStorage.Category.SIMPLE_MODE, oid=self.conf.oid)
        if load_from_backend:
            self.switch_simple_mode(False)
        elif clientSimple is not None:
            self.switch_simple_mode(clientSimple)

    def update_ui_games(self, update_state):
        self.hold()
        for i in range(1, self.sets_limit + 1):
            teamA_game_int = update_state.get_game(1, i)
            teamB_game_int = update_state.get_game(2, i)
            if (i == self.current_set):
                self.teamAButton.set_text(f'{teamA_game_int:02d}')
                self.teamBButton.set_text(f'{teamB_game_int:02d}')
            self.main_state.set_game(i, 1, str(teamA_game_int))
            self.main_state.set_game(i, 2, str(teamB_game_int))
        self.update_ui_games_table(update_state)
        self.release()

    def update_ui_games_table(self, update_state):
        logo1 = self.current_customize_state.get_team_logo(1)
        logo2 = self.current_customize_state.get_team_logo(2)
        self.scores.clear()
        with self.scores:
            if (logo1 is not None and logo1 != Customization.DEFAULT_IMAGE):
                ui.image(source=logo1).classes('w-6 h-6 m-auto')
            else:
                ui.icon(name='sports_volleyball', color='blue', size='xs')

            if (logo2 is not None and logo2 != Customization.DEFAULT_IMAGE):
                ui.image(source=logo2).classes('w-6 h-6 m-auto')
            else:
                ui.icon(name='sports_volleyball', color='red', size='xs')
            lastWithoutZeroZero = 1
            match_finished = self.match_finished(
                update_state.get_sets(1), update_state.get_sets(2))
            for i in range(1, self.sets_limit + 1):
                teamA_game_int = update_state.get_game(1, i)
                teamB_game_int = update_state.get_game(2, i)
                if (teamA_game_int + teamB_game_int > 0):
                    lastWithoutZeroZero = i

            for i in range(1, self.sets_limit + 1):
                teamA_game_int = update_state.get_game(1, i)
                teamB_game_int = update_state.get_game(2, i)
                if (i > 1 and i > lastWithoutZeroZero):
                    break
                if (i == self.current_set and i < self.sets_limit and not match_finished):
                    break
                label1 = ui.label(f'{teamA_game_int:02d}').classes('p-0')
                label2 = ui.label(f'{teamB_game_int:02d}').classes('p-0')
                if (teamA_game_int > teamB_game_int):
                    label1.classes('text-bold')
                elif (teamA_game_int < teamB_game_int):
                    label2.classes('text-bold')

    def update_ui_timeouts(self, update_state):
        self.hold()
        self.change_ui_timeout(1, update_state.get_timeout(1))
        self.change_ui_timeout(2, update_state.get_timeout(2))
        self.release()

    def update_ui_serve(self, update_state):
        """
        Actualiza los iconos de servicio basándose en el estado actual.
        """
        self.hold()
        current_serve = update_state.get_current_serve()
        
        # Icon color directly reflects the state
        self.serveA.props(f'color={TACOLOR_HIGH if current_serve == State.SERVE_1 else TACOLOR_VLIGHT}')
        self.serveB.props(f'color={TBCOLOR_HIGH if current_serve == State.SERVE_2 else TBCOLOR_VLIGHT}')
        self.release()

    def update_ui_sets(self, update_state):
        self.hold()
        t1sets = update_state.get_sets(1)
        t2sets = update_state.get_sets(2)
        self.main_state.set_sets(1, str(t1sets))
        self.main_state.set_sets(2, str(t2sets))
        self.teamASet.set_text(str(t1sets))
        self.teamBSet.set_text(str(t2sets))
        self.release()

    def update_ui_current_set(self, set_number):
        self.hold()
        self.main_state.set_current_set(set_number)
        self.set_selector.set_value(set_number)
        self.release()

    def update_ui_visible(self, enabled):
        icon = 'visibility' if enabled else 'visibility_off'
        color = VISIBLE_ON_COLOR if enabled else VISIBLE_OFF_COLOR
        self.visibility_button.set_icon(icon)
        self.visibility_button.props(f'color={color}')

    def hold(self):
        self.holdUpdate += 1

    def release(self):
        if self.holdUpdate > 0:
            self.holdUpdate -= 1

    def release_hold_and_send_state(self):
        self.release()
        if self.holdUpdate == 0:
            self.send_state()

    def send_state(self):
        if (self.holdUpdate == 0):
            self.backend.save(self.main_state, self.simple)

    def reset(self):
        self.logger.info('Reset called')
        self.backend.reset(self.main_state)
        self.update_ui(True)

    def change_serve(self, team, force=False):
        current_serve = self.main_state.get_current_serve()
        new_serve = State.SERVE_NONE
        if team == 1:
            if force or current_serve != State.SERVE_1:
                new_serve = State.SERVE_1
        elif team == 2:
            if force or current_serve != State.SERVE_2:
                new_serve = State.SERVE_2
        self.main_state.set_current_serve(new_serve)
        self.update_ui_serve(self.main_state)
        self.send_state()

    def add_timeout(self, team):
        color = TACOLOR_MEDIUM if team == 1 else TBCOLOR_MEDIUM
        container = self.timeoutsA if team == 1 else self.timeoutsB

        if self.undo:
            if container.default_slot.children:
                container.remove(0)
            self.switch_undo(True)
        else:
            if len(container.default_slot.children) < 2:
                with container:
                    ui.icon(name='radio_button_unchecked',
                              color=color, size='12px').classes('text-center')
            else:
                container.clear()
        self.main_state.set_timeout(
            team, len(container.default_slot.children))
        self.send_state()

    def change_ui_timeout(self, team, value):
        color = TACOLOR_MEDIUM if team == 1 else TBCOLOR_MEDIUM
        container = self.timeoutsA if team == 1 else self.timeoutsB
        container.clear()
        with container:
            for _ in range(value):
                ui.icon(name='radio_button_unchecked',
                          color=color, size='12px')
        self.main_state.set_timeout(team, value)

    def set_game_value(self, team: int, value: int):
        """Directly sets the game score for a team."""
        self.hold()
        self.main_state.set_game(self.current_set, team, value)
        self.update_ui_games(self.main_state)
        self.release_hold_and_send_state()

    def set_sets_value(self, team: int, value: int):
        """Directly sets the sets won for a team."""
        self.hold()
        self.main_state.set_sets(team, value)
        self.update_ui_sets(self.main_state)
        self.switch_to_set(self.compute_current_set(self.main_state))
        self.release_hold_and_send_state()

    def add_game(self, team):
        if self.block_additional_points():
            return

        self.hold()

        button = self.teamAButton if team == 1 else self.teamBButton
        rival_button = self.teamBButton if team == 1 else self.teamAButton
        rival_score = int(rival_button.text)
        self.change_serve(team, True)

        current = self.add_int_to_button(button)
        self.main_state.set_game(self.current_set, team, current)

        if self.conf.auto_hide:
            if self.hide_timer:
                self.hide_timer.cancel()
            self.switch_visibility(True)

        if (current >= self.get_game_limit(self.current_set) and (current - rival_score > 1)):
            self.add_set(team)
            if self.conf.auto_simple_mode:
                self.switch_simple_mode(False)
        else:
            if self.conf.auto_hide:
                self.hide_timer = ui.timer(
                    self.conf.hide_timeout, lambda: self.switch_visibility(False), once=True)
            if self.conf.auto_simple_mode:
                self.switch_simple_mode(True)

        self.release_hold_and_send_state()

    def set_team_name(self, team, name):
        self.main_state.set_team_name(team, name)

    def get_team_name(self, team):
        return self.main_state.get_team_name(team)

    def get_current_model(self):
        return self.main_state.get_current_model()

    def is_show_logos(self):
        return self.main_state.is_show_logos()

    def set_show_logos(self, show):
        self.main_state.set_show_logos(show)

    def get_game_limit(self, set_number):
        return self.points_limit_last_set if set_number == self.sets_limit else self.points_limit

    def add_set(self, team, roll2zero=True):
        if self.block_additional_points():
            return

        self.hold()
        button = self.teamASet if team == 1 else self.teamBSet
        soft_limit = 2 if self.sets_limit == 3 else 3
        limit = soft_limit if roll2zero else soft_limit + 1
        current = self.add_int_to_button(button, limit, False)

        self.main_state.set_sets(team, current)
        self.change_ui_timeout(1, 0)
        self.change_ui_timeout(2, 0)
        self.change_serve(0)
        self.switch_to_set(self.compute_current_set(self.main_state))
        self.release()

    def block_additional_points(self):
        t1sets = self.main_state.get_sets(1)
        t2sets = self.main_state.get_sets(2)
        return not self.undo and self.match_finished(t1sets, t2sets)

    def switch_to_set(self, set_number):
        if (self.current_set != set_number):
            self.current_set = set_number
            self.update_ui_current_set(self.current_set)
            self.update_ui_games(self.main_state)

    def switch_visibility(self, force_value=None):
        update = False
        if self.visible and force_value is not True:
            self.visible = False
            update = True
        elif not self.visible and force_value is not False:
            self.visible = True
            update = True

        if update:
            self.update_ui_visible(self.visible)
            self.backend.change_overlay_visibility(self.visible)

    def switch_simple_mode(self, force_value=None):
        self.hold()
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
        self.release_hold_and_send_state()

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

    def add_int_to_button(self, button, limit=99, force_digits=True):
        current = int(button.text)
        if self.undo:
            if (current != 0):
                current -= 1
            self.switch_undo(True)
        else:
            current += 1
        if current > limit:
            current = 0

        text_format = '{:02d}' if force_digits else '{:01d}'
        button.set_text(text_format.format(current))
        return current

    def refresh(self):
        self.update_ui(True)