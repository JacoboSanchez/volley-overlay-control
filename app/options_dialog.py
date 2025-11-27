from nicegui import ui
from app.conf import Conf
from app.messages import Messages
from app.app_storage import AppStorage
from app.theme import *
import logging

class OptionsDialog:

    def __init__(self, configuration: Conf):
        self.configuration = configuration
        self.dialog = ui.dialog()
        self.dark_mode = ui.dark_mode()
        self.on_change_callback = None
        saved_dark_mode_option = AppStorage.load(AppStorage.Category.DARK_MODE, default=None)
        logging.debug('loaded dark mode %s', saved_dark_mode_option)
        if saved_dark_mode_option == None:
            saved_dark_mode_option = self.configuration.darkMode
        logging.info('Setting dark mode %s', saved_dark_mode_option)
        self.set_ui_dark_mode(saved_dark_mode_option)
        with self.dialog, ui.card():
            ui.label(Messages.get(Messages.OPTIONS_TITLE)).classes('text-lg font-semibold')
            with ui.card():
                ui.label(Messages.get(Messages.HIDE_OPTIONS)).classes('text-lg font-semibold')
                self.auto_hide_switch = ui.switch(
                    Messages.get(Messages.AUTO_HIDE),
                    on_change=self.on_auto_hide_change
                )

                with ui.column().classes('w-full gap-0 pt-2'):
                    self.hide_timeout_label = ui.label()
                    self.hide_timeout_slider = ui.slider(min=1, max=15, step=1, on_change=self.on_hide_timeout_change) \
                        .bind_enabled_from(self.auto_hide_switch, 'value')

                self.auto_simple_mode_switch = ui.switch(
                    Messages.get(Messages.AUTO_SIMPLE_MODE),
                    on_change=self.on_auto_simple_mode_change
                )
                with ui.row().classes('w-full'):
                    self.auto_simple_mode_timeout_switch = ui.switch(
                        Messages.get(Messages.AUTO_SIMPLE_MODE_TIMEOUT_ON_TIMEOUT),
                        on_change=self.on_auto_simple_mode_timeout_change
                    ).bind_enabled_from(self.auto_simple_mode_switch, 'value')

            ui.separator()
            with ui.card().classes('w-full'):
                ui.label(Messages.get(Messages.BUTTON_COLORS_SECTION)).classes('text-lg font-semibold')
                
                self.follow_team_colors_switch = ui.switch(
                    Messages.get(Messages.FOLLOW_TEAM_COLORS),
                    on_change=self.on_follow_team_colors_change
                ).mark('follow-team-colors-switch')

                follow_team = AppStorage.load(AppStorage.Category.BUTTONS_FOLLOW_TEAM_COLORS, False, oid=self.configuration.oid)
                initial_classes = 'max-h-0 opacity-0' if follow_team else 'max-h-[200px] opacity-100'
                
                self.custom_colors_container = ui.column().classes(f'w-full gap-2 transition-all duration-300 ease-in-out overflow-hidden {initial_classes}')
                with self.custom_colors_container:
                     with ui.row().classes('w-full items-center justify-between'):
                        ui.label(Messages.get(Messages.LOCAL))
                        with ui.row():
                            self.create_color_picker(AppStorage.Category.TEAM_1_BUTTON_COLOR, DEFAULT_BUTTON_A_COLOR, tooltip=Messages.get(Messages.BUTTON_COLOR), marker='color-picker-team-1-btn')
                            with ui.element('div').classes('w-2'): pass
                            self.create_color_picker(AppStorage.Category.TEAM_1_BUTTON_TEXT_COLOR, DEFAULT_BUTTON_TEXT_COLOR, tooltip=Messages.get(Messages.BUTTON_TEXT_COLOR), marker='color-picker-team-1-text')

                     with ui.row().classes('w-full items-center justify-between'):
                        ui.label(Messages.get(Messages.VISITOR))
                        with ui.row():
                            self.create_color_picker(AppStorage.Category.TEAM_2_BUTTON_COLOR, DEFAULT_BUTTON_B_COLOR, tooltip=Messages.get(Messages.BUTTON_COLOR), marker='color-picker-team-2-btn')
                            with ui.element('div').classes('w-2'): pass
                            self.create_color_picker(AppStorage.Category.TEAM_2_BUTTON_TEXT_COLOR, DEFAULT_BUTTON_TEXT_COLOR, tooltip=Messages.get(Messages.BUTTON_TEXT_COLOR), marker='color-picker-team-2-text')

            ui.separator()
            with ui.card().classes('w-full'):
                ui.label(Messages.get(Messages.VISUALIZATION_OPTIONS)).classes('text-lg font-semibold')
                with ui.row().classes('justify-center'):
                    self.fullscreen = ui.fullscreen(on_value_change=self.full_screen_updated)
                    self.fullscreenButton = ui.button(icon='fullscreen', color=COLOR_FULLSCREEN_BUTTON,
                                                    on_click=self.fullscreen.toggle).props(
                        'outline color=' + COLOR_FULLSCREEN_BUTTON).classes('w-8 h-8 m-auto')
                    self.update_full_screen_icon()
                    ui.space()
                    self.slider = ui.slide_item()
                    with self.slider:
                        with ui.item():
                            with ui.item_section():
                                with ui.row():
                                    ui.icon('dark_mode')
                                    ui.icon('multiple_stop')
                                    ui.icon('light_mode', color='amber')
                        with self.slider.right(color='black', on_slide=lambda: self.switch_darkmode('on')):
                            ui.icon('dark_mode')
                        with self.slider.left(color='white', on_slide=lambda: self.switch_darkmode('off')):
                            ui.icon('light_mode', color='amber')
                        self.slider.top('auto', color='gray-400', on_slide=lambda: self.switch_darkmode('auto'))
            
            ui.button(Messages.get(Messages.CLOSE), on_click=self.dialog.close).props('flat').classes('w-full mt-4')

    def full_screen_updated(self, e):
        self.update_full_screen_icon(e.value)

    def update_full_screen_icon(self, inputValue=None):
        value = inputValue
        if inputValue is None:
            value = self.fullscreen.value
        logging.debug('value %s', value)
        if value:
            self.fullscreenButton.icon = 'fullscreen_exit'
            self.fullscreenButton.props('color=' + COLOR_EXIT_FULLSCREEN_BUTTON)
        else:
            self.fullscreenButton.icon = 'fullscreen'
            self.fullscreenButton.props('color=' + COLOR_FULLSCREEN_BUTTON)

    def switch_darkmode(self, value: str):
        self.set_ui_dark_mode(value)
        AppStorage.save(AppStorage.Category.DARK_MODE, value)
        self.slider.reset()

    def set_ui_dark_mode(self, darkMode: str):
        logging.debug('Setting dark mode %s', darkMode)
        match darkMode:
            case 'on':
                self.dark_mode.enable()
            case 'off':
                self.dark_mode.disable()
            case 'auto':
                self.dark_mode.auto()

    def on_auto_hide_change(self, e):
        AppStorage.save(AppStorage.Category.AUTOHIDE_ENABLED, e.value, oid=self.configuration.oid)

    def on_hide_timeout_change(self, e):
        self.hide_timeout_label.set_text(f"{Messages.get(Messages.HIDE_TIMEOUT)}: {int(e.value)}s")
        AppStorage.save(AppStorage.Category.AUTOHIDE_SECONDS, int(e.value), oid=self.configuration.oid)

    def on_auto_simple_mode_change(self, e):
        AppStorage.save(AppStorage.Category.SIMPLIFY_OPTION_ENABLED, e.value, oid=self.configuration.oid)
        if not e.value:
            self.auto_simple_mode_timeout_switch.value = False
            AppStorage.save(AppStorage.Category.SIMPLIFY_ON_TIMEOUT_ENABLED, False, oid=self.configuration.oid)

    def on_auto_simple_mode_timeout_change(self, e):
        AppStorage.save(AppStorage.Category.SIMPLIFY_ON_TIMEOUT_ENABLED, e.value, oid=self.configuration.oid)

    def create_color_picker(self, storage_key, default_value, tooltip=None, marker=None):
        color_btn = ui.button().classes('w-6 h-6 border')
        if marker:
            color_btn.mark(marker)
        initial_color = AppStorage.load(storage_key, default_value, oid=self.configuration.oid)
        color_btn.style(f'background-color: {initial_color} !important')
        
        with color_btn:
            if tooltip:
                ui.tooltip(tooltip)
            ui.color_picker(on_pick=lambda e: self.update_color(e, color_btn, storage_key))
        
    def update_color(self, e, button, storage_key):
        button.style(f'background-color: {e.color} !important')
        AppStorage.save(storage_key, e.color, oid=self.configuration.oid)
        if self.on_change_callback:
            self.on_change_callback()

    def on_follow_team_colors_change(self, e):
        AppStorage.save(AppStorage.Category.BUTTONS_FOLLOW_TEAM_COLORS, e.value, oid=self.configuration.oid)
        if e.value:
            self.custom_colors_container.classes(remove='max-h-[200px] opacity-100', add='max-h-0 opacity-0')
        else:
            self.custom_colors_container.classes(remove='max-h-0 opacity-0', add='max-h-[200px] opacity-100')
            
        if self.on_change_callback:
            self.on_change_callback()

    def set_callback(self, callback):
        self.on_change_callback = callback

    def open(self):
        auto_hide = AppStorage.load(AppStorage.Category.AUTOHIDE_ENABLED, oid=self.configuration.oid)
        if auto_hide is None:
            auto_hide = self.configuration.auto_hide
        self.auto_hide_switch.value = auto_hide

        hide_timeout = AppStorage.load(AppStorage.Category.AUTOHIDE_SECONDS, oid=self.configuration.oid)
        if hide_timeout is None:
            hide_timeout = self.configuration.hide_timeout
        self.hide_timeout_slider.value = hide_timeout
        self.hide_timeout_label.set_text(f"{Messages.get(Messages.HIDE_TIMEOUT)}: {hide_timeout}s")

        auto_simple_mode = AppStorage.load(AppStorage.Category.SIMPLIFY_OPTION_ENABLED, oid=self.configuration.oid)
        if auto_simple_mode is None:
            auto_simple_mode = self.configuration.auto_simple_mode
        self.auto_simple_mode_switch.value = auto_simple_mode

        auto_simple_mode_timeout = AppStorage.load(AppStorage.Category.SIMPLIFY_ON_TIMEOUT_ENABLED, oid=self.configuration.oid)
        if auto_simple_mode_timeout is None:
            auto_simple_mode_timeout = self.configuration.auto_simple_mode_timeout
        self.auto_simple_mode_timeout_switch.value = auto_simple_mode_timeout

        follow_team = AppStorage.load(AppStorage.Category.BUTTONS_FOLLOW_TEAM_COLORS, False, oid=self.configuration.oid)
        self.follow_team_colors_switch.value = follow_team
        
        if follow_team:
            self.custom_colors_container.classes(remove='max-h-[200px] opacity-100', add='max-h-0 opacity-0')
        else:
            self.custom_colors_container.classes(remove='max-h-0 opacity-0', add='max-h-[200px] opacity-100')

        self.dialog.open()