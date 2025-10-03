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
    card_height = card_width * 9 / 16
    iframe_width = 600
    iframe_height = iframe_width * 9 / 16  # As in original code

    # --- New Calculation Logic based on user premises ---

    # 1. Calculate the dimensions of the desired region in pixels.
    # `width` and `height` are given in a [0, 100] range from the abstract coordinate system.
    region_width_px = (width / 100) * iframe_width
    region_height_px = (height / 100) * iframe_height

    # 2. Define the object's center in the [-50, 50] coordinate system,
    #    and calculate the top-left corner of the bounding box in the same system.
    # Width is symmetrical around xpos.
    left_coord = xpos - width / 2
    # Height is asymmetrical (5 parts up, 7 parts down) around ypos.
    top_coord = ypos - height * (5 / 17)

    # 3. Convert the top-left corner to iframe pixel coordinates. This determines the iframe's offset.
    # The coordinate system range is 100 (from -50 to 50).
    left_px = ((left_coord + 50) / 100) * iframe_width
    top_px = ((top_coord + 50) / 100) * iframe_height

    # 4. Calculate the scale factor to fit the selected region into the card.
    scale = 1
    if region_width_px > 0 and region_height_px > 0:
        scale = min(card_width / region_width_px, card_height / region_height_px)

    # --- HTML/CSS for display ---
    # The outer div is the fixed-size card.
    # The inner div contains the selected iframe region and is scaled to fit inside the card.
    
    ui.html(f'''
    <div style="width: {card_width}px; height: {card_height}px; overflow: hidden; display: flex; justify-content: center; align-items: center;">
        <div style="width: {region_width_px}px; height: {region_height_px*8/10}px; overflow: hidden; position: relative; transform: scale({scale}); transform-origin: center center;">
            <iframe src="{url}" width="{iframe_width}px" height="{iframe_height}px" style="border: 0; position: absolute; top: {-top_px}px; left: {-left_px}px;"></iframe>
        </div>
    </div>
    ''', sanitize=False).mark('preview-iframe')