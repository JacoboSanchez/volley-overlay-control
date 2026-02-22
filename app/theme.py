"""
Centralized theme and style constants for the application's UI.
"""

# Team A Colors
TACOLOR = 'blue'
TACOLOR_VLIGHT = 'indigo-5'
TACOLOR_LIGHT = 'indigo-5'
TACOLOR_MEDIUM = 'indigo-5'
TACOLOR_HIGH = 'indigo-5'

# Team B Colors
TBCOLOR = 'red'
TBCOLOR_VLIGHT = 'indigo-5'
TBCOLOR_LIGHT = 'indigo-5'
TBCOLOR_MEDIUM = 'indigo-5'
TBCOLOR_HIGH = 'indigo-5'

# Other UI Colors
DO_COLOR = 'indigo-700'
UNDO_COLOR = 'indigo-400'
VISIBLE_ON_COLOR = 'green-600'
VISIBLE_OFF_COLOR = 'green-800'
FULL_SCOREBOARD_COLOR = 'orange-500'
SIMPLE_SCOREBOARD_COLOR = 'orange-700'
RED_BUTTON_COLOR = 'red'
BLUE_BUTTON_COLOR = 'blue'

# Button Styles
GAME_BUTTON_PADDING_NORMAL = 'p-0'
GAME_BUTTON_TEXT_NORMAL = 'text-6xl'
GAME_BUTTON_CLASSES = ' text-center align-middle shadow-lg rounded-lg text-white h-auto min-h-0 '

# Font Scaling Multipliers to normalize visual size inside buttons
# Format: 'Font Name': {'scale': float, 'offset_y': float}
# offset_y specifices vertical translation percentage (negative moves text up, positive moves down) relative to button size.
FONT_SCALES = {
    'Default': {'scale': 1.0, 'offset_y': 0.0},
    'Digital Dismay': {'scale': 1.16, 'offset_y': 0.01},
    'Aluminum': {'scale': 1.06, 'offset_y': 0.02},
    'Atlas': {'scale': 0.96, 'offset_y': 0.01},
    'Bypass': {'scale': 0.96, 'offset_y': 0.0},
    'Catch': {'scale': 1.17, 'offset_y': 0.01},
    'Devotee': {'scale': 1.14, 'offset_y': 0.02},
    'Digital Readout': {'scale': 1.39, 'offset_y': 0.0},
    'LED board': {'scale': 0.79, 'offset_y': -0.01},
    'Open 24': {'scale': 1.14, 'offset_y': -0.02},
    'Alarm Clock': {'scale': 1.01, 'offset_y': 0.01},
}

# Control buttons
CONTROL_BUTTON_CLASSES = 'w-9 h-9 rounded-lg'

# Default Button Colors
DEFAULT_BUTTON_A_COLOR = '#2196f3' # Blue
DEFAULT_BUTTON_B_COLOR = '#f44336' # Red
DEFAULT_BUTTON_TEXT_COLOR = '#ffffff'

# General UI Constants
DIALOG_CARD_CLASSES = 'relative w-full max-w-4xl p-0'
SECTION_CARD_CLASSES = 'w-full p-2 shadow-none'
SECTION_TITLE_CLASSES = 'text-base font-semibold text-primary'
SWITCH_CLASSES = 'w-full'
CLOSE_BUTTON_PROPS = 'flat round dense size=sm'
CLOSE_BUTTON_CLASSES = 'absolute top-2 right-2 z-10'
ICON_BUTTON_PROPS = 'flat round dense'
ROW_CENTER_CLASSES = 'items-center w-full'