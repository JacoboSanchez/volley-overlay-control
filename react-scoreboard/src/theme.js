/**
 * Theme constants matching the NiceGUI scoreboard theme.
 */

// Team A (Home) colors
export const TEAM_A_COLOR = '#2196f3'; // Blue
export const TEAM_A_LIGHT = '#5c6bc0'; // Indigo-5
export const TEAM_A_SERVE_ACTIVE = '#5c6bc0';
export const TEAM_A_SERVE_INACTIVE = '#5c6bc0';

// Team B (Away) colors
export const TEAM_B_COLOR = '#f44336'; // Red
export const TEAM_B_LIGHT = '#5c6bc0'; // Indigo-5
export const TEAM_B_SERVE_ACTIVE = '#5c6bc0';
export const TEAM_B_SERVE_INACTIVE = '#5c6bc0';

// Control button colors
export const VISIBLE_ON_COLOR = '#2e7d32'; // green-600
export const VISIBLE_OFF_COLOR = '#1b5e20'; // green-800
export const FULL_SCOREBOARD_COLOR = '#ff9800'; // orange-500
export const SIMPLE_SCOREBOARD_COLOR = '#e65100'; // orange-700
export const UNDO_COLOR = '#5c6bc0'; // indigo-400
export const DO_COLOR = '#303f9f'; // indigo-700

// Default button colors
export const DEFAULT_BUTTON_A_COLOR = '#2196f3';
export const DEFAULT_BUTTON_B_COLOR = '#f44336';
export const DEFAULT_BUTTON_TEXT_COLOR = '#ffffff';

// Font scales for score buttons — matches app/theme.py FONT_SCALES
export const FONT_SCALES = {
  Default:           { scale: 1.0,  offset_y: 0.0 },
  'Digital Dismay':  { scale: 1.16, offset_y: 0.01 },
  Aluminum:          { scale: 1.06, offset_y: 0.02 },
  Atlas:             { scale: 0.96, offset_y: 0.01 },
  Bypass:            { scale: 0.96, offset_y: 0.0 },
  Catch:             { scale: 1.17, offset_y: 0.01 },
  Devotee:           { scale: 1.14, offset_y: 0.02 },
  'Digital Readout': { scale: 1.39, offset_y: 0.0 },
  'LED board':       { scale: 0.79, offset_y: -0.01 },
  'Open 24':         { scale: 1.14, offset_y: -0.02 },
  'Alarm Clock':     { scale: 1.01, offset_y: 0.01 },
};

// Font names available for the score button selector
export const FONT_OPTIONS = Object.keys(FONT_SCALES);
