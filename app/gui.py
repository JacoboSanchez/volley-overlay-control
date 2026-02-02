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

    def is_portrait(width, height):
        return height > 1.2 * width and not width > 800

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
        self.preview_card_width = 250
        self.PADDINGS = GAME_BUTTON_PADDING_NORMAL
        self.TEXTSIZE = GAME_BUTTON_TEXT_NORMAL
        self.hide_timer = None
        self.long_press_timer = None
        self.teamA_logo = None
        self.teamB_logo = None
        self.teamA_scores_container = None
        self.teamB_scores_container = None
        # Flag to control event processing gate
        self.click_gate_open = True
        self.preview_container = None
        self.preview_button = None
        self.preview_visible = self.conf.show_preview
        self.main_container = None
        self.is_portrait = False
        self.current_panel_style = None
        self.main_conainer_layout = None
        self.current_dimension = None
        self.button_size = None
        self.button_text_size = None

        self.dark_mode = ui.dark_mode()
        self.fullscreen = ui.fullscreen()


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

    async def set_page_size(self, width, height):
        """Adjusts UI element sizes based on page dimensions."""
        self.page_height = height
        self.page_width = width
        current_portrait = self.is_portrait
        self.is_portrait = GUI.is_portrait(self.page_width, self.page_height)
        self.logger.debug('Set page size to: %sx%s',
                         self.page_height, self.page_width)
        
        if not self.is_portrait:
            dimension = self.page_width
            self.preview_card_width = self.page_width/4
            self.button_size = self.page_width / 4.5
        else: 
            dimension = self.page_height
            self.button_size = self.page_height / 5

        self.button_text_size = self.button_size / 2
        
        self.logger.debug('Dimension: %s, Button Size: %s', dimension, self.button_size)
        if self.main_container is not None and (self.current_dimension is None or self.current_dimension != dimension or current_portrait != self.is_portrait):
            self.logger.debug('Reinitializing main container due to orientation change.')
            self.main_container.clear()
            await self._initialize_main_container()
        self.current_dimension = dimension
        
        self.update_button_style()

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
                    await self.create_iframe()
        elif self.preview_container is not None:
            self.preview_container.clear()

    def _create_team_panel(self, team_id, button_color, timeout_light_color, serve_vlight_color):
        """Creates the UI panel for a single team."""
        with ui.card(align_items='begin'):
            with ui.row() if self.is_portrait else ui.column():
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
                button.classes(GAME_BUTTON_CLASSES)

                if self.is_portrait:
                    with ui.column().classes('text-4xl h-full'):
                        serve_icon = ui.icon(
                            name='sports_volleyball', color=serve_vlight_color).mark(f'team-{team_id}-serve')
                        ui.space()
                        ui.button(icon='timer', color=timeout_light_color,
                                on_click=lambda: self.add_timeout(team_id)).props('outline round').mark(f'team-{team_id}-timeout').classes('shadow-lg')
                        timeouts = ui.row().mark(f'team-{team_id}-timeouts-display')
                        serve_icon.on('click', lambda: self.change_serve(team_id))  
                else: 
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
        with ui.column().classes('h-full'):
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

                with ui.row().classes('justify-center items-start gap-x-2'):
                    with ui.column().classes('items-center gap-y-0'):
                        logo1_src = self.current_customize_state.get_team_logo(1)
                        self.teamA_logo = ui.image(source=logo1_src).classes('w-6 h-6').mark('team-1-logo')
                        self.teamA_scores_container = ui.column().classes('items-center gap-y-0 min-h-24')

                    with ui.column().classes('items-center gap-y-0'):
                        logo2_src = self.current_customize_state.get_team_logo(2)
                        self.teamB_logo = ui.image(source=logo2_src).classes('w-6 h-6').mark('team-2-logo')
                        self.teamB_scores_container = ui.column().classes('items-center gap-y-0 min-h-24')

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
            
            if self.conf.show_preview and self.conf.output is not None:
                self.preview_container = ui.column()
                if self.preview_visible:
                    with self.preview_container:
                        await self.create_iframe()

    def _update_dark_mode_icon(self):
        if self.dark_mode_button:
             if self.dark_mode.value is True:
                 self.dark_mode_button.props('icon=dark_mode')
             elif self.dark_mode.value is False:
                 self.dark_mode_button.props('icon=light_mode')
             else:
                 self.dark_mode_button.props('icon=brightness_auto')

    async def _cycle_dark_mode(self):
        if self.dark_mode.value is True:
            self.dark_mode.disable() # Go to Light
        elif self.dark_mode.value is False:
            self.dark_mode.auto() # Go to Auto
        else:
            self.dark_mode.enable() # Go to Dark
        
        self._update_dark_mode_icon()
        AppStorage.save(AppStorage.Category.DARK_MODE, 'on' if self.dark_mode.value is True else 'off' if self.dark_mode.value is False else 'auto')

        if self.preview_visible and self.preview_container is not None:
             self.preview_container.clear()
             with self.preview_container:
                 await self.create_iframe()

    def _create_control_buttons(self):
        """Creates the main control buttons (visibility, simple mode, undo, etc.)."""
        def button_classes():
            return CONTROL_BUTTON_CLASSES

        with ui.row().classes("w-full justify-around"):
            self.visibility_button = ui.button(icon='visibility',
                                               on_click=self.switch_visibility).props(f'outline color={VISIBLE_ON_COLOR}').mark('visibility-button').classes(button_classes())
            self.simple_button = ui.button(icon='grid_on',
                                           on_click=self.switch_simple_mode).props(f'outline color={FULL_SCOREBOARD_COLOR}').mark('simple-mode-button').classes(button_classes())

            self.undo_button = ui.button(icon='undo', on_click=lambda: self.switch_undo(
                False)).props(f'outline color={UNDO_COLOR}').mark('undo-button').classes(button_classes())
            if not self.conf.disable_overview and self.conf.output is not None:
                icon = GUI.PREVIEW_ENABLED_ICON if self.preview_visible else GUI.PREVIEW_DISABLED_ICON
                self.preview_button = ui.button(icon=icon, on_click=self.toggle_preview).props(
                        'outline').mark('preview-button').classes(button_classes()).classes('text-gray-500')
            ui.space()
            # Dark Mode
            self.dark_mode_button = ui.button(on_click=self._cycle_dark_mode).props('outline color=indigo-5').classes(button_classes()).classes('text-gray-500')
            self._update_dark_mode_icon()

            # Fullscreen
            self.fullscreen_button = ui.button(icon='fullscreen', on_click=self.fullscreen.toggle).props('outline color=light-green-10').classes(button_classes()).classes('text-gray-500')
            def update_fs_icon(e):
                self.fullscreen_button.props(f'icon={"fullscreen_exit" if e.value else "fullscreen"}')
            self.fullscreen.on_value_change(update_fs_icon)

            
            
            ui.button(icon='keyboard_arrow_right', on_click=lambda: self.tabs.set_value(
                Customization.CONFIG_TAB)).props('outline color=stone-500').mark('config-tab-button').classes(button_classes())

    async def init(self, force=True, custom_points_limit=None, custom_points_limit_last_set=None, custom_sets_limit=None):
        if self.initialized and not force:
            return

        # Restore dark mode
        saved_dark_mode = AppStorage.load(AppStorage.Category.DARK_MODE, 'auto')
        if saved_dark_mode == 'on':
             self.dark_mode.enable()
        elif saved_dark_mode == 'off':
             self.dark_mode.disable()
        else:
             self.dark_mode.auto()

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
        self.main_container = ui.element('div').classes('w-full h-full')
        await self._initialize_main_container()
        self._create_control_buttons()

        self.update_ui(False)
        self.initialized = True
        self.logger.info('Initialized gui')

    async def _initialize_main_container(self):
        if self.main_conainer_layout is not None:
            self.main_conainer_layout.clear()
        with self.main_container:
            with ui.column(align_items='center').classes('w-full') if self.is_portrait else ui.row().classes('w-full') as self.main_conainer_layout:
                self.teamAButton, self.timeoutsA, self.serveA = self._create_team_panel(
                    1, BLUE_BUTTON_COLOR, TACOLOR_LIGHT, TACOLOR_VLIGHT)
                ui.space()
                await self._create_center_panel()
                ui.space()
                self.teamBButton, self.timeoutsB, self.serveB = self._create_team_panel(
                    2, RED_BUTTON_COLOR, TBCOLOR_LIGHT, TBCOLOR_VLIGHT)
                
                # Apply configured styles after creation
                self.update_button_style()
                
                current_state = self.game_manager.get_current_state()
                self.update_ui_timeouts(current_state)
                self.update_ui_games(current_state)

                self.update_ui_sets(current_state)
                self.current_set = self.compute_current_set(current_state)
                self.update_ui_current_set(self.current_set)
                self.update_ui_serve(current_state)


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

    def update_button_style(self):
        """Updates the style of the score buttons based on configuration."""
        follow_team_colors = AppStorage.load(AppStorage.Category.BUTTONS_FOLLOW_TEAM_COLORS, False)
        
        if follow_team_colors:
            color1 = self.current_customize_state.get_team_color(1)
            text1 = self.current_customize_state.get_team_text_color(1)
            color2 = self.current_customize_state.get_team_color(2)
            text2 = self.current_customize_state.get_team_text_color(2)
        else:
            color1 = AppStorage.load(AppStorage.Category.TEAM_1_BUTTON_COLOR, DEFAULT_BUTTON_A_COLOR)
            text1 = AppStorage.load(AppStorage.Category.TEAM_1_BUTTON_TEXT_COLOR, DEFAULT_BUTTON_TEXT_COLOR)
            color2 = AppStorage.load(AppStorage.Category.TEAM_2_BUTTON_COLOR, DEFAULT_BUTTON_B_COLOR)
            text2 = AppStorage.load(AppStorage.Category.TEAM_2_BUTTON_TEXT_COLOR, DEFAULT_BUTTON_TEXT_COLOR)
        
        # Determine font style
        selected_font = AppStorage.load(AppStorage.Category.SELECTED_FONT, 'Default')
        font_style = ""
        if selected_font and selected_font != 'Default':
             font_style = f"font-family: '{selected_font}' !important;"

        # Size styles
        size_style = ""
        if self.button_size:
            size_style = f"width: {self.button_size}px !important; height: {self.button_size}px !important;"
        
        text_size_style = ""
        if self.button_text_size:
            text_size_style = f"font-size: {self.button_text_size}px !important;"

        # Helper to generate style string including background
        def get_team_style(team_id, base_color, text_color):
            style_parts = [
                f'background-color: {base_color} !important',
                f'color: {text_color} !important',
                font_style,
                size_style,
                text_size_style
            ]
            
            show_icon = AppStorage.load(AppStorage.Category.BUTTONS_SHOW_ICON, False)
            if show_icon:
                logo_url = self.current_customize_state.get_team_logo(team_id)
                if logo_url:
                    icon_opacity = float(AppStorage.load(AppStorage.Category.BUTTONS_ICON_OPACITY, 0.3))
                    
                    # Calculate overlay color for opacity simulation
                    overlay_rgba = None
                    if base_color and base_color.startswith('#') and len(base_color) == 7:
                        try:
                            c = base_color.lstrip('#')
                            rgb = tuple(int(c[i:i+2], 16) for i in (0, 2, 4))
                            # We overlay the background color with (1 - opacity) to fade the icon
                            overlay_alpha = 1.0 - icon_opacity
                            overlay_rgba = f"rgba({rgb[0]}, {rgb[1]}, {rgb[2]}, {overlay_alpha:.2f})"
                        except Exception as e:
                            self.logger.error(f"Error parsing color {base_color}: {e}")
                            pass
                    
                    if overlay_rgba:
                         style_parts.append(f"background-image: linear-gradient({overlay_rgba}, {overlay_rgba}), url('{logo_url}') !important")
                    else:
                         style_parts.append(f"background-image: url('{logo_url}') !important")
                         style_parts.append("background-blend-mode: overlay !important")

                    style_parts.append("background-size: contain !important")
                    style_parts.append("background-repeat: no-repeat !important")
                    style_parts.append("background-position: center !important")
            
            return '; '.join([s for s in style_parts if s])

        # Apply styles, removing the default text-white class to allow custom text colors
        if self.teamAButton:
            self.teamAButton.classes(remove='text-white')
            self.teamAButton.style(replace=get_team_style(1, color1, text1))
            
        if self.teamBButton:
            self.teamBButton.classes(remove='text-white')
            self.teamBButton.style(replace=get_team_style(2, color2, text2))
            
        # Apply font style to set buttons as well
        if self.teamASet:
            self.teamASet.style(replace=f'{font_style}')

        if self.teamBSet:
             self.teamBSet.style(replace=f'{font_style}')

    def update_ui(self, load_from_backend=False):
        self.logger.debug('Updating UI...')
        if load_from_backend:
            self.logger.info('loading data from backend')
            self.game_manager = GameManager(self.conf, self.backend)
            self.current_customize_state.set_model(
                self.backend.get_current_customization())
            self.visible = self.backend.is_visible()
            self.update_ui_logos()
        self.update_button_style()

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
        if self.teamA_scores_container is None or self.teamB_scores_container is None:
            return
            
        self.teamA_scores_container.clear()
        self.teamB_scores_container.clear()

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
            do_break = False
            empty_label = False
            if i > 1 and i > lastWithoutZeroZero:
                do_break = True
            if i == self.current_set and i < self.sets_limit and not match_finished:
                do_break = True
            if do_break: 
                break


            with self.teamA_scores_container:
                label1 = ui.label(f'{teamA_game_int:02d}').classes('p-0 m-0').mark(f'team-1-set-{i}-score')
            with self.teamB_scores_container:
                label2 = ui.space() if empty_label else ui.label(f'{teamB_game_int:02d}').classes('p-0 m-0').mark(f'team-2-set-{i}-score')

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
        
        is_serving_a = current_serve == State.SERVE_1
        self.serveA.props(f'color={TACOLOR_HIGH if is_serving_a else TACOLOR_VLIGHT}')
        self.serveA.style(f'opacity: {1 if is_serving_a else 0.4}')

        is_serving_b = current_serve == State.SERVE_2
        self.serveB.props(f'color={TBCOLOR_HIGH if is_serving_b else TBCOLOR_VLIGHT}')
        self.serveB.style(f'opacity: {1 if is_serving_b else 0.4}')

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
        stored = AppStorage.load(AppStorage.Category.AUTOHIDE_ENABLED)
        if stored is not None:
            return stored
        return self.conf.auto_hide

    def get_hide_timeout(self):
        stored = AppStorage.load(AppStorage.Category.AUTOHIDE_SECONDS)
        if stored is not None:
            return int(stored)
        return self.conf.hide_timeout

    def is_auto_simple_mode_enabled(self):
        stored = AppStorage.load(AppStorage.Category.SIMPLIFY_OPTION_ENABLED)
        if stored is not None:
            return stored
        return self.conf.auto_simple_mode

    def is_auto_simple_mode_timeout_enabled(self):
        stored = AppStorage.load(AppStorage.Category.SIMPLIFY_ON_TIMEOUT_ENABLED)
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

    async def create_iframe(self):
        ui.separator()
        is_dark = self.dark_mode.value
        # If auto (None), we might default to False or try to detect.
        # However, passing None to create_iframe_card will trigger the JS detection, which is what we want for Auto.
        # But if we just switched to Auto, JS might need a moment.
        # Let's pass the explicit boolean if set, otherwise None.
        await create_iframe_card(self.conf.output, self.current_customize_state.get_h_pos(), self.current_customize_state.get_v_pos(), self.current_customize_state.get_width(), self.current_customize_state.get_height(), self.preview_card_width, dark_mode=is_dark)