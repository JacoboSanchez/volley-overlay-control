import os
from nicegui import ui
from app.preview import create_iframe_card

class PreviewPage:
    
    def __init__(self, xpos: float = -20, ypos: float = -10, width: float = 40, height: float = 12, output: str = None):
        self.xpos = xpos
        self.ypos = ypos
        self.width = width
        self.height = height
        self.output = output
        self.page_height = None
        self.page_width = None
        self.dark_mode = ui.dark_mode()
        self.fullscreen = ui.fullscreen()
        self.scale_factor = 1.0
        self._is_rendering = False
        self.dark_enabled = False
      
    async def initialize(self):  
        if "PYTEST_CURRENT_TEST" not in os.environ:
            self.dark_enabled = await ui.run_javascript('Quasar.Dark.isActive')

        with ui.column().classes('w-full items-center'):
            self.frame_container = ui.row()
        with ui.footer(value=True).classes('bg-transparent'):
            with ui.row().classes('w-full items-center p-2'):
                self.size_down = ui.button(icon='remove', on_click=self.decrease_scale).props('outline')
                self.size_up = ui.button(icon='add', on_click=self.increase_scale).props('outline')
                ui.space()
                self.dark_button = ui.button(icon='dark_mode', on_click=self.toggle_dark_mode).props('outline')
                self.fullscreen_button = ui.button(icon='fullscreen', on_click=self.toggle_fullscreen).props('outline')
        self.customize_buttons()
        
    async def set_page_size(self, width: int, height: int):
        is_first_load = self.page_height is None or self.page_width is None
        self.page_height = height
        self.page_width = width
        
        if is_first_load:
            await self.create_page()
        else:
            await self._update_iframe()
        

    async def create_page(self):
        if not self.output:
            ui.label("Output token is missing.")
            return
        
        if self.page_width is not None and self.page_height is not None:
            await self._update_iframe()

    async def increase_scale(self):
        self.scale_factor = round(min(2.0, self.scale_factor + 0.2), 2)
        await self._update_iframe()

    async def decrease_scale(self):
        self.scale_factor = round(max(0.5, self.scale_factor - 0.2), 2)
        await self._update_iframe()

    async def toggle_dark_mode(self):
        if "PYTEST_CURRENT_TEST" not in os.environ:
            self.dark_enabled = await ui.run_javascript('Quasar.Dark.isActive')
        self.dark_mode.set_value(not self.dark_enabled)
        self.dark_enabled = not self.dark_enabled
        self.customize_buttons()   
        await self._update_iframe()

    def customize_buttons(self):
#        color = "#AAAAAA" if self.dark_enabled else "#333333"
#        self.size_down.classes(f'!text-[{color}]')
#        self.size_up.classes(f'!text-[{color}]')
#        self.dark_button.classes(f'!text-[{color}]')
#        self.fullscreen_button.classes(f'!text-[{color}]')

        if self.dark_enabled:
            self.dark_button.set_icon('light_mode')
        else:
            self.dark_button.set_icon('dark_mode')
        

    async def toggle_fullscreen(self):
        self.fullscreen.toggle()

    async def _update_iframe(self):
        if self.frame_container is None:
            return
        if self._is_rendering:
            return
        self._is_rendering = True
        try:
            self.frame_container.clear()
            if self.page_width is not None and self.page_height is not None:
                with self.frame_container:
                    card_width = (600 if self.page_height is None or self.page_width is None else self.page_width / 1.2) * self.scale_factor
                    await create_iframe_card(self.output, self.xpos, self.ypos, self.width, self.height, card_width)
        finally:
            self._is_rendering = False