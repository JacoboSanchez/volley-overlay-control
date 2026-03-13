import logging
from app.theme import (
    FONT_SCALES,
    DEFAULT_BUTTON_A_COLOR, DEFAULT_BUTTON_B_COLOR, DEFAULT_BUTTON_TEXT_COLOR,
)
from app.app_storage import AppStorage


def update_button_style(teamAButton, teamBButton, teamASet, teamBSet,
                        button_size, button_text_size, customize_state, logger=None,
                        local_settings=None):
    """Updates the style of the score buttons based on configuration.

    local_settings: optional dict with pre-loaded per-instance visual settings.
    When provided it is used instead of AppStorage so that broadcasts to other
    browser tabs always apply the *target* tab's own preferences.
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    def _load(key, default):
        if local_settings is not None:
            return local_settings.get(key, default)
        return AppStorage.load(key, default)

    follow_team_colors = _load(AppStorage.Category.BUTTONS_FOLLOW_TEAM_COLORS, False)

    if follow_team_colors:
        color1 = customize_state.get_team_color(1)
        text1 = customize_state.get_team_text_color(1)
        color2 = customize_state.get_team_color(2)
        text2 = customize_state.get_team_text_color(2)
    else:
        color1 = _load(AppStorage.Category.TEAM_1_BUTTON_COLOR, DEFAULT_BUTTON_A_COLOR)
        text1 = _load(AppStorage.Category.TEAM_1_BUTTON_TEXT_COLOR, DEFAULT_BUTTON_TEXT_COLOR)
        color2 = _load(AppStorage.Category.TEAM_2_BUTTON_COLOR, DEFAULT_BUTTON_B_COLOR)
        text2 = _load(AppStorage.Category.TEAM_2_BUTTON_TEXT_COLOR, DEFAULT_BUTTON_TEXT_COLOR)

    # Determine font style
    selected_font = _load(AppStorage.Category.SELECTED_FONT, 'Default')
    font_style = ""
    font_scale = 1.0
    font_offset_y = 0.0
    if selected_font and selected_font != 'Default':
        font_style = f"font-family: '{selected_font}' !important;"
        font_props = FONT_SCALES.get(selected_font, {'scale': 1.0, 'offset_y': 0.0})
        if isinstance(font_props, dict):
            font_scale = font_props.get('scale', 1.0)
            font_offset_y = font_props.get('offset_y', 0.0)
        else:
            font_scale = font_props

    # Size styles
    size_style = ""
    padding_style = ""
    if button_size:
        size_style = f"width: {button_size}px !important; height: {button_size}px !important;"
        if font_offset_y != 0.0:
            offset_px = button_size * font_offset_y * 2.0
            if offset_px < 0:
                padding_style = f"padding-bottom: {abs(offset_px)}px !important; padding-top: 0px !important;"
            else:
                padding_style = f"padding-top: {abs(offset_px)}px !important; padding-bottom: 0px !important;"

    text_size_style = ""
    if button_text_size:
        scaled_text_size = button_text_size * font_scale
        text_size_style = f"font-size: {scaled_text_size}px !important; line-height: 1.0 !important;"

    def get_team_style(team_id, base_color, text_color):
        style_parts = [
            f'background-color: {base_color} !important',
            f'color: {text_color} !important',
            font_style,
            size_style,
            text_size_style,
            padding_style,
        ]

        show_icon = _load(AppStorage.Category.BUTTONS_SHOW_ICON, False)
        if show_icon:
            logo_url = customize_state.get_team_logo(team_id)
            if logo_url:
                icon_opacity = float(_load(AppStorage.Category.BUTTONS_ICON_OPACITY, 0.3))

                overlay_rgba = None
                if base_color and base_color.startswith('#') and len(base_color) == 7:
                    try:
                        c = base_color.lstrip('#')
                        rgb = tuple(int(c[i:i+2], 16) for i in (0, 2, 4))
                        overlay_alpha = 1.0 - icon_opacity
                        overlay_rgba = f"rgba({rgb[0]}, {rgb[1]}, {rgb[2]}, {overlay_alpha:.2f})"
                    except Exception as e:
                        logger.error(f"Error parsing color {base_color}: {e}")

                if overlay_rgba:
                    style_parts.append(f"background-image: linear-gradient({overlay_rgba}, {overlay_rgba}), url('{logo_url}') !important")
                else:
                    style_parts.append(f"background-image: url('{logo_url}') !important")
                    style_parts.append("background-blend-mode: overlay !important")

                style_parts.append("background-size: contain !important")
                style_parts.append("background-repeat: no-repeat !important")
                style_parts.append("background-position: center !important")

        return '; '.join([s for s in style_parts if s])

    if teamAButton:
        teamAButton.classes(remove='text-white')
        teamAButton.style(replace=get_team_style(1, color1, text1))

    if teamBButton:
        teamBButton.classes(remove='text-white')
        teamBButton.style(replace=get_team_style(2, color2, text2))

    # Apply font style to set buttons
    set_button_style = font_style
    if font_scale != 1.0:
        set_button_style += f" font-size: {24 * font_scale}px !important; line-height: 1.0 !important;"
    if font_offset_y != 0.0:
        offset_px_set = 24 * font_scale * font_offset_y * 2.0
        if offset_px_set < 0:
            set_button_style += f" padding-bottom: {abs(offset_px_set)}px !important; padding-top: 0px !important;"
        else:
            set_button_style += f" padding-top: {abs(offset_px_set)}px !important; padding-bottom: 0px !important;"

    if teamASet:
        teamASet.style(replace=set_button_style.strip())

    if teamBSet:
        teamBSet.style(replace=set_button_style.strip())
