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
        self.frame_container = ui.row().classes('w-full')
        self.dark_mode = ui.dark_mode()
        
    async def set_page_size(self, width: int, height: int):
        rebuild = self.page_height is None or self.page_width is None
        self.page_height = height
        self.page_width = width
        if rebuild: 
            self.frame_container.clear()
            await self.create_page()
        

    async def create_page(self):
        if not self.output:
            ui.label("Output token is missing.")
            return
        if self.page_width is not None and self.page_height is not None:
            self.dark_mode.auto()            
            card_width = 600 if self.page_height is None or self.page_width is None else self.page_width/1.2
            with self.frame_container:
                await create_iframe_card(self.output, self.xpos, self.ypos, self.width, self.height, card_width)

            
    