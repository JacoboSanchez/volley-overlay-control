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
export const VISIBLE_ON_COLOR = '#4caf50'; // Bright green for better contrast
export const VISIBLE_OFF_COLOR = '#f44336'; // Bright red for better contrast
export const FULL_SCOREBOARD_COLOR = '#ff9800'; // orange-500
export const SIMPLE_SCOREBOARD_COLOR = '#e65100'; // orange-700
export const UNDO_COLOR = '#b0bcff'; // light periwinkle, high contrast on dark navy
export const PREVIEW_ON_COLOR = '#e040fb'; // purple-A200, vivid magenta
export const PREVIEW_OFF_COLOR = '#ab47bc'; // purple-400, dimmer but still visible on dark

// Default button colors
export const DEFAULT_BUTTON_A_COLOR = '#2196f3';
export const DEFAULT_BUTTON_B_COLOR = '#f44336';
export const DEFAULT_BUTTON_TEXT_COLOR = '#ffffff';

// Font scales for score buttons — matches app/theme.py FONT_SCALES
export interface FontScale {
  scale: number;
  offset_y: number;
  /**
   * Horizontal ink compensation in em. Some score fonts centre the
   * glyph *advance* but not the visible ink (asymmetric side
   * bearings — LED board's digits sit a uniform 0.07em left of
   * their advance centre), so a centred flex box shows the number
   * off to one side. There is no CSS metric override for horizontal
   * bearings, so the measured imbalance (fontTools ink bbox vs
   * advance width, mean over 0-9) is compensated with a translateX
   * of ``offset_x * fontSize`` in ScoreButton. Unlike vertical
   * metrics, horizontal ones render identically on every platform,
   * so a static measured value is safe.
   */
  offset_x: number;
}

// Fallback used whenever a font name has no entry in FONT_SCALES; also the
// value seeded under the ``Default`` key below. Exported so callers can
// reach it without needing an indexed access (which is `T | undefined`
// under noUncheckedIndexedAccess).
export const DEFAULT_FONT_SCALE: FontScale = { scale: 1.0, offset_y: 0.0, offset_x: 0.0 };

// ``offset_y`` is 0 across the board since the @font-face metric
// overrides in App.css centre each font's digits exactly (computed
// from the glyph geometry); the field stays so operators with stale
// settings and future odd fonts keep an escape hatch.
export const FONT_SCALES: Record<string, FontScale> = {
  Default: DEFAULT_FONT_SCALE,
  'Digital Dismay': { scale: 1.16, offset_y: 0.0, offset_x: 0.007 },
  Aluminum: { scale: 1.06, offset_y: 0.0, offset_x: 0.0 },
  Atlas: { scale: 0.96, offset_y: 0.0, offset_x: 0.0 },
  Bypass: { scale: 0.96, offset_y: 0.0, offset_x: 0.0 },
  Catch: { scale: 1.17, offset_y: 0.0, offset_x: 0.0 },
  Devotee: { scale: 1.14, offset_y: 0.0, offset_x: 0.0 },
  'Digital Readout': { scale: 1.39, offset_y: 0.0, offset_x: -0.017 },
  'LED board': { scale: 0.79, offset_y: 0.0, offset_x: 0.07 },
  'Open 24': { scale: 1.14, offset_y: 0.0, offset_x: 0.029 },
  'Alarm Clock': { scale: 1.01, offset_y: 0.0, offset_x: 0.014 },
};

// Font names available for the score button selector
export const FONT_OPTIONS = Object.keys(FONT_SCALES);
