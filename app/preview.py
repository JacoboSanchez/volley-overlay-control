from nicegui import ui
import os
from app.state import State


async def create_iframe_card(url: str, xpos: int, ypos: int, width: int, height: int, card_width: int=250, dark_mode: bool=None, layout_id: str=None):
    championship_layout = layout_id == State.CHAMPIONSHIP_LAYOUT_ID
    """Creates a NiceGUI card with a specific region of an iframe, scaled to a fixed size."""
    dark_enabled = False
    if dark_mode is not None:
        dark_enabled = dark_mode
    elif "PYTEST_CURRENT_TEST" not in os.environ:
        try:
            dark_enabled = await ui.run_javascript('Quasar.Dark.isActive', timeout=3.0)
        except Exception:
            dark_enabled = False
        
    is_custom_overlay = layout_id and (str(layout_id).startswith('C-') or str(layout_id) == 'auto')
    
    if not is_custom_overlay and url:
        is_custom_overlay = 'overlays.uno' not in url

    if not is_custom_overlay:
        separator = "&" if "?" in url else "?"
        background = f"{separator}bgcolor=rgb(29, 29, 29)&aspect=16:9" if dark_enabled else f"{separator}bgcolor=white"
        url = url + background

    card_height = card_width * height / width
    iframe_width = 600
    iframe_height = iframe_width * 9 / 16  # As in original code

    if is_custom_overlay:
        import uuid
        container_id = f"preview-container-{uuid.uuid4().hex[:8]}"
        
        # We assume 16:9 for the preview card, matching the overlay's aspect ratio
        custom_card_height = card_width * 9 / 16
        custom_iframe_width = 1920
        custom_iframe_height = 1080

        ui.html(f'''
        <div id="{container_id}" style="width: {card_width}px; height: {custom_card_height}px; overflow: hidden; display: flex; justify-content: center; align-items: center; position: relative;">
            <div class="iframe-wrapper" style="position: absolute; width: {custom_iframe_width}px; height: {custom_iframe_height}px; transform-origin: top left; transform: scale(0.12); top: 0; left: 0; opacity: 0; transition: opacity 0.3s ease;">
                <iframe src="{url}" width="{custom_iframe_width}px" height="{custom_iframe_height}px" style="border: 0;"></iframe>
            </div>
        </div>
        ''', sanitize=False).mark('preview-iframe-custom')

        ui.run_javascript(f'''
            setTimeout(() => {{
                const container = document.getElementById("{container_id}");
                if (!container) return;
                const wrapper = container.querySelector(".iframe-wrapper");
                
                function onMessage(event) {{
                    if (event.data && event.data.type === 'overlayRenderArea') {{
                        const bounds = event.data.bounds;
                        if (bounds.width > 0 && bounds.height > 0) {{
                            const cWidth = container.clientWidth;
                            const cHeight = container.clientHeight;
                            
                            const scaleX = cWidth / bounds.width;
                            const scaleY = cHeight / bounds.height;
                            const scale = Math.min(scaleX, scaleY) * 0.95; // 0.95 gives a small margin
                            
                            const scaledWidth = bounds.width * scale;
                            const scaledHeight = bounds.height * scale;
                            
                            const offsetX = (cWidth - scaledWidth) / 2 - (bounds.x * scale);
                            const offsetY = (cHeight - scaledHeight) / 2 - (bounds.y * scale);
                            
                            wrapper.style.transform = `translate(${{offsetX}}px, ${{offsetY}}px) scale(${{scale}})`;
                            wrapper.style.opacity = '1';
                        }}
                    }}
                }}
                window.addEventListener("message", onMessage);
            }}, 100);
        ''')
        return

    # 1. Calculate the dimensions of the desired region in pixels.
    # `width` and `height` are given in a [0, 100] range from the abstract coordinate system.
    region_width_px = (width / 100) * iframe_width
    region_height_px = (height / (60 if championship_layout else 100)) * iframe_height

    # 2. Define the object's center in the [-50, 50] coordinate system,
    #    and calculate the top-left corner of the bounding box in the same system.
    # Width is symmetrical around xpos.
    left_coord = xpos - width / 2
    # Height is asymmetrical (5 parts up, 7 parts down) around ypos.
    top_coord = ypos - height * (5 / 17)

    # 3. Convert the top-left corner to iframe pixel coordinates. This determines the iframe's offset.
    # The coordinate system range is 100 (from -50 to 50).
    left_px = ((left_coord + 50) / 100) * iframe_width
    
    if championship_layout:
        top_px = (top_coord / 100) * iframe_height
    else:
        top_px = ((top_coord + 50) / 100) * iframe_height

    # 4. Calculate the scale factor to fit the selected region into the card.
    scale = 1
    if region_width_px > 0 and region_height_px > 0:
        scale = min(card_width / region_width_px, card_height / region_height_px)

    # --- HTML/CSS for display ---
    # The outer div is the fixed-size card.
    # The inner div contains the selected iframe region and is scaled to fit inside the card.
    ui.html(f'''
    <div style="width: {card_width}px; height: {card_height/2}px; overflow: hidden; display: flex; justify-content: center; align-items: center;">
        <div style="width: {region_width_px}px; height: {region_height_px*8/10}px; overflow: hidden; position: relative; transform: scale({scale}); transform-origin: center center;">
            <iframe src="{url}" width="{iframe_width}px" height="{iframe_height}px" style="border: 0; position: absolute; top: {-top_px}px; left: {-left_px}px;"></iframe>
        </div>
    </div>
    ''', sanitize=False).mark('preview-iframe')