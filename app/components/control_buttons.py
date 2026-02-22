from nicegui import ui
from app.theme import CONTROL_BUTTON_CLASSES, VISIBLE_ON_COLOR, FULL_SCOREBOARD_COLOR, UNDO_COLOR
from app.customization import Customization

class ControlButtons:
    def __init__(self, gui):
        self.gui = gui

    def create(self):
        with ui.row().classes("w-full justify-around"):
            self.gui.visibility_button = ui.button(
                icon='visibility',
                on_click=self.gui.switch_visibility
            ).props(f'outline color={VISIBLE_ON_COLOR}').mark('visibility-button').classes(CONTROL_BUTTON_CLASSES)
            
            self.gui.simple_button = ui.button(
                icon='grid_on',
                on_click=self.gui.switch_simple_mode
            ).props(f'outline color={FULL_SCOREBOARD_COLOR}').mark('simple-mode-button').classes(CONTROL_BUTTON_CLASSES)

            self.gui.undo_button = ui.button(
                icon='undo', on_click=lambda: self.gui.switch_undo(False)
            ).props(f'outline color={UNDO_COLOR}').mark('undo-button').classes(CONTROL_BUTTON_CLASSES)
            
            if not self.gui.conf.disable_overview and self.gui.conf.output is not None:
                icon = self.gui.PREVIEW_ENABLED_ICON if self.gui.preview_visible else self.gui.PREVIEW_DISABLED_ICON
                self.gui.preview_button = ui.button(
                    icon=icon, on_click=self.gui.toggle_preview
                ).props('outline').mark('preview-button').classes(CONTROL_BUTTON_CLASSES).classes('text-gray-500')
            
            ui.space()
            
            ui.button(
                icon='keyboard_arrow_right', 
                on_click=lambda: self.gui.tabs.set_value(Customization.CONFIG_TAB)
            ).props('outline color=stone-500').mark('config-tab-button').classes(CONTROL_BUTTON_CLASSES)
