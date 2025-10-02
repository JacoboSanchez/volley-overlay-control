from nicegui import ui
import os


async def create_iframe_card(url: str, xpos: int, ypos: int, width: int, height: int):
    """Creates a NiceGUI card with a specific region of an iframe, scaled to a fixed size."""
    
    dark_enabled = False
    if "PYTEST_CURRENT_TEST" not in os.environ:
        dark_enabled = await ui.run_javascript('Quasar.Dark.isActive')
    background = '?bgcolor=rgb(29, 29, 29)' if dark_enabled else '?bgcolor=white'
    url = url + background
    card_width = 250
    card_height = card_width*9/16
    xfactor = 5
    yfactor = xfactor*card_height/card_width
    iframe_width = 100*xfactor
    iframe_height = 100*yfactor
    xpos = xpos*xfactor
    ypos = ypos*yfactor
    width = width*xfactor
    height = height*yfactor
    # Calculate the top and left positions to center the desired region
    left = width / 2.0 - iframe_width / 2.0 - xpos
    top = height / 2.0 - iframe_height / 2.0 - ypos

    # Calculate the scale factor
    scale = min(card_width / width, card_height / height) if width > 0 and height > 0 else 1
    ui.separator()
    ui.html(f'''
    <div style="width: {card_width}px; height: {height*scale}px; overflow: hidden; display: flex; justify-content: center; align-items: center;">
        <div style="width: {width}px; height: {height}px; overflow: hidden; position: relative; transform: scale({scale}); transform-origin: center center;">
            <iframe src="{url}" width="{iframe_width}px" height="{iframe_height}px" style="border: 0; position: absolute; top: {top}px; left: {left}px;"></iframe>
        </div>
    </div>
    ''').mark('preview-iframe')