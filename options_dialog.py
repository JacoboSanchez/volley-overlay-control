from nicegui import ui
from conf import Conf
from messages import Messages
from app_storage import AppStorage
import logging

class OptionsDialog:
    COLOR_FULLSCREEN_BUTTON = 'gray-400'
    COLOR_EXIT_FULLSCREEN_BUTTON = 'gray-600'

    def __init__(self, configuration: Conf):
        self.configuration = configuration
        self.dialog = ui.dialog()
        self.dark_mode = ui.dark_mode()
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
                auto_hide_switch = ui.switch(
                    Messages.get(Messages.AUTO_HIDE),
                    value=self.configuration.auto_hide,
                    on_change=self.on_auto_hide_change
                )

                with ui.column().classes('w-full gap-0 pt-2'):
                    ui.label().bind_text_from(self.configuration, 'hide_timeout',
                                            lambda v: f"{Messages.get(Messages.HIDE_TIMEOUT)}: {v}s")
                    ui.slider(min=1, max=15, step=1, on_change=self.on_hide_timeout_change) \
                        .bind_value(self.configuration, 'hide_timeout').bind_enabled_from(auto_hide_switch, 'value')

                ui.switch(
                    Messages.get(Messages.AUTO_SIMPLE_MODE),
                    value=self.configuration.auto_simple_mode,
                    on_change=self.on_auto_simple_mode_change
                )

            ui.separator()
            with ui.card().classes('w-full'):
                ui.label(Messages.get(Messages.VISUALIZATION_OPTIONS)).classes('text-lg font-semibold')
                with ui.row().classes('justify-center'):
                    self.fullscreen = ui.fullscreen(on_value_change=self.full_screen_updated)
                    self.fullscreenButton = ui.button(icon='fullscreen', color=self.COLOR_FULLSCREEN_BUTTON,
                                                    on_click=self.fullscreen.toggle).props(
                        'outline color=' + self.COLOR_FULLSCREEN_BUTTON).classes('w-8 h-8 m-auto')
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
            self.fullscreenButton.props('color=' + self.COLOR_EXIT_FULLSCREEN_BUTTON)
        else:
            self.fullscreenButton.icon = 'fullscreen'
            self.fullscreenButton.props('color=' + self.COLOR_FULLSCREEN_BUTTON)

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
        self.configuration.auto_hide = e.value
        AppStorage.save(AppStorage.Category.AUTOHIDE_ENABLED, e.value)

    def on_hide_timeout_change(self, e):
        AppStorage.save(AppStorage.Category.AUTOHIDE_SECONDS, int(e.value))

    def on_auto_simple_mode_change(self, e):
        self.configuration.auto_simple_mode = e.value
        AppStorage.save(AppStorage.Category.SIMPLIFY_OPTION_ENABLED, e.value)

    def open(self):
        self.dialog.open()
