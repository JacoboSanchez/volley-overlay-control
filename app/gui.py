import logging
import weakref
from nicegui import ui
from nicegui.client import Client
from app.customization import Customization
from app.app_storage import AppStorage
from app.messages import Messages
from app.theme import *
from app.game_manager import GameManager
from app.preview import create_iframe_card
from app.components.team_panel import TeamPanel
from app.components.center_panel import CenterPanel
from app.components.control_buttons import ControlButtons
from app.components.button_interaction import ButtonInteraction
from app.gui_update_mixin import UIUpdateMixin


class GUI(UIUpdateMixin):
    # Class-level registry of active GUI instances for multi-user broadcast
    _instances = weakref.WeakSet()

    @staticmethod
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
        self.teamA_logo = None
        self.teamB_logo = None
        self.teamA_scores_container = None
        self.teamB_scores_container = None
        self.preview_container = None
        self.preview_button = None
        self.preview_visible = self.conf.show_preview
        self.main_container = None
        self.is_portrait = False
        self.current_panel_style = None
        self.main_conainer_layout = None
        self.current_dimension = None
        self.rebuild_dimension = None
        self.rebuild_width = None
        self.rebuild_height = None
        self.button_size = None
        self.button_text_size = None

        # Button interaction handler (tap, double-tap, long-press)
        self.interaction = ButtonInteraction(self)

        # Initialize dark mode and fullscreen reading from persistent storage
        saved_dark_mode = AppStorage.load(AppStorage.Category.DARK_MODE, 'auto')
        init_val = True if saved_dark_mode == 'on' else False if saved_dark_mode == 'off' else None
        self.dark_mode = ui.dark_mode(value=init_val)
        self.fullscreen = ui.fullscreen()

        # Register this instance for multi-user broadcast
        GUI._instances.add(self)
        self._client = ui.context.client

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
                ui.button(Messages.get(Messages.OK), icon='done', color=None, on_click=self._handle_custom_value_submit).props('flat').classes('text-green-500').mark('value-input-ok-button')
                ui.button(Messages.get(Messages.CANCEL), icon='close', color=None, on_click=self.custom_value_dialog.close).props('flat').classes('text-red-500').mark('value-input-cancel-button')

    def set_customization_model(self, model):
        """Directly sets the customization model from an external source."""
        self.logger.debug("Setting customization model directly.")
        self.current_customize_state.set_model(model)

    async def set_page_size(self, width, height):
        """Adjusts UI element sizes based on page dimensions."""
        if width <= 0 or height <= 0:
            return

        self.page_height = height
        self.page_width = width

        self.logger.debug(f'Resize Event: {self.page_width}x{self.page_height}')

        # Hysteresis Logic for Orientation
        new_is_portrait = self.is_portrait

        if width > 800:
            new_is_portrait = False
        else:
            ratio = height / width
            if self.is_portrait:
                if ratio < 1.1:
                    new_is_portrait = False
            else:
                if ratio > 1.3:
                    new_is_portrait = True

        significant_resize = False
        if self.main_container is not None:
            if self.rebuild_width is None or self.rebuild_height is None:
                significant_resize = True
            else:
                width_diff = abs(self.page_width - self.rebuild_width)
                height_diff = abs(self.page_height - self.rebuild_height)
                if width_diff > 50 or height_diff > 50:
                    significant_resize = True

        orientation_changed = (new_is_portrait != self.is_portrait)
        should_rebuild = orientation_changed or (self.main_container is not None and self.rebuild_width is None)

        if should_rebuild or significant_resize:

            self.is_portrait = new_is_portrait

            if not self.is_portrait:
                dimension = self.page_width
                self.preview_card_width = self.page_width / 4
                self.button_size = self.page_width / 4.5
            else:
                dimension = self.page_height
                self.button_size = self.page_height / 5

            self.button_text_size = self.button_size / 2

            if should_rebuild:
                self.logger.debug('Set page size to: %sx%s. Rebuilding (Orientation Change/Init).',
                                  self.page_height, self.page_width)
                self.logger.debug('Dimension: %s, Button Size: %s', dimension, self.button_size)
                self.logger.debug('Reinitializing main container...')
                self.main_container.clear()
                await self._initialize_main_container()
            else:
                self.logger.debug('Set page size to: %sx%s. Resize only (No Rebuild).',
                                  self.page_height, self.page_width)

            self.rebuild_dimension = dimension
            self.rebuild_width = self.page_width
            self.rebuild_height = self.page_height
            self.current_dimension = dimension

            self.update_button_style()

    def _handle_custom_value_submit(self):
        """Submits the value from the reusable dialog."""
        self.custom_value_dialog.submit(self.dialog_input.value)

    async def show_custom_value_dialog(self, team: int, is_set_button: bool, initial_value: int, max_value: int):
        """Opens a reusable dialog to set a custom value for points or sets."""
        title = Messages.get(Messages.SET_CUSTOM_SET_VALUE) if is_set_button else Messages.get(Messages.SET_CUSTOM_GAME_VALUE)

        self.dialog_team = team
        self.dialog_is_set = is_set_button

        self.dialog_label.set_text(title)
        self.dialog_input.label = Messages.get(Messages.VALUE)
        self.dialog_input.value = initial_value
        self.dialog_input.min = 0
        self.dialog_input.max = max_value

        result = await self.custom_value_dialog

        if result is not None:
            value = int(result)
            if self.dialog_is_set:
                self.set_sets_value(self.dialog_team, value)
            else:
                self.set_game_value(self.dialog_team, value)

        self.interaction.open_click_gate()

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
        self.logger.info('Set points last set: %s', self.points_limit_last_set)
        self.logger.info('Sets to win: %s', self.sets_limit)
        self.main_container = ui.element('div').classes('w-full h-full')
        await self._initialize_main_container()
        ControlButtons(self).create()

        self.update_ui(False)
        self.initialized = True
        self.logger.info('Initialized gui')

    async def _initialize_main_container(self):
        if self.main_conainer_layout is not None:
            self.main_conainer_layout.clear()
        with self.main_container:
            with ui.column(align_items='center').classes('w-full') if self.is_portrait else ui.row().classes('w-full') as self.main_conainer_layout:
                self.teamAButton, self.timeoutsA, self.serveA = TeamPanel(
                    self, 1, BLUE_BUTTON_COLOR, TACOLOR_LIGHT, TACOLOR_VLIGHT).create()
                ui.space()
                await CenterPanel(self).create()
                ui.space()
                self.teamBButton, self.timeoutsB, self.serveB = TeamPanel(
                    self, 2, RED_BUTTON_COLOR, TBCOLOR_LIGHT, TBCOLOR_VLIGHT).create()

                self.update_button_style()

                current_state = self.game_manager.get_current_state()
                self.update_ui_timeouts(current_state)
                self.update_ui_games(current_state)
                self.update_ui_sets(current_state)
                self.current_set = self.compute_current_set(current_state)
                self.update_ui_current_set(self.current_set)
                self.update_ui_serve(current_state)

    def send_state(self):
        """Sends the current state to the backend and broadcasts to other clients."""
        self.game_manager.save(self.simple, self.current_set)
        self._broadcast_to_others()

    async def reset(self):
        """Resets the game state, saves it, and updates the UI."""
        self.logger.debug('Reset called')
        self.game_manager.reset()
        self.update_ui(load_from_backend=True)

    async def refresh(self):
        """Reloads the game state from the backend and updates the UI."""
        self.logger.debug('Refresh called, reloading state from backend.')
        self.update_ui(load_from_backend=True)

    def _broadcast_to_others(self):
        """Notify all other connected GUI instances to refresh their UI."""
        for instance in GUI._instances:
            if instance is not self and instance.initialized:
                client = getattr(instance, '_client', None)
                if client is None or client.id not in Client.instances:
                    continue
                try:
                    instance.update_ui(load_from_backend=True)
                except Exception as e:
                    self.logger.debug(f'Broadcast to other client failed: {e}')

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

    def set_game_value(self, team: int, value: int):
        """Directly sets the game score for a team."""
        self.game_manager.set_game_value(team, value, self.current_set)

        set_won = self.game_manager.check_set_won(
            team, self.current_set, self.points_limit, self.points_limit_last_set, self.sets_limit
        )

        current_state = self.game_manager.get_current_state()
        self.teamAButton.set_text(f'{current_state.get_game(1, self.current_set):02d}')
        self.teamBButton.set_text(f'{current_state.get_game(2, self.current_set):02d}')

        if set_won:
            self.update_ui_sets(current_state)
            self.update_ui_timeouts(current_state)
            if not self.game_manager.match_finished():
                self.switch_to_set(self.compute_current_set(current_state))

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
        await create_iframe_card(self.conf.output, self.current_customize_state.get_h_pos(), self.current_customize_state.get_v_pos(), self.current_customize_state.get_width(), self.current_customize_state.get_height(), self.preview_card_width, dark_mode=is_dark, layout_id=self.conf.id)
