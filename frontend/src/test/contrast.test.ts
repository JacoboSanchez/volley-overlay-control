import { describe, it, expect } from 'vitest';
import {
  contrastRatio,
  getReadableOnSurface,
  hslToRgb,
  parseHexColor,
  relativeLuminance,
  rgbToHex,
  rgbToHsl,
} from '../utils/contrast';

describe('parseHexColor', () => {
  it('parses 6-digit hex strings', () => {
    expect(parseHexColor('#1a73e8')).toEqual({ r: 26, g: 115, b: 232 });
  });

  it('parses 3-digit shorthand', () => {
    expect(parseHexColor('#abc')).toEqual({ r: 170, g: 187, b: 204 });
  });

  it('accepts hex without leading #', () => {
    expect(parseHexColor('ff8800')).toEqual({ r: 255, g: 136, b: 0 });
  });

  it('returns null for invalid input', () => {
    expect(parseHexColor('not-a-color')).toBeNull();
    expect(parseHexColor('#12345')).toBeNull();
    expect(parseHexColor('#zzzzzz')).toBeNull();
  });
});

describe('relativeLuminance & contrastRatio', () => {
  it('returns 0 for black and 1 for white', () => {
    expect(relativeLuminance({ r: 0, g: 0, b: 0 })).toBeCloseTo(0, 4);
    expect(relativeLuminance({ r: 255, g: 255, b: 255 })).toBeCloseTo(1, 4);
  });

  it('returns 21 for black on white (WCAG max)', () => {
    const ratio = contrastRatio({ r: 0, g: 0, b: 0 }, { r: 255, g: 255, b: 255 });
    expect(ratio).toBeCloseTo(21, 1);
  });

  it('is symmetric', () => {
    const a = { r: 26, g: 115, b: 232 };
    const b = { r: 22, g: 33, b: 62 };
    expect(contrastRatio(a, b)).toBeCloseTo(contrastRatio(b, a), 6);
  });
});

describe('rgbToHsl / hslToRgb round-trip', () => {
  it.each([
    [{ r: 26, g: 115, b: 232 }],
    [{ r: 244, g: 67, b: 54 }],
    [{ r: 92, g: 107, b: 192 }],
    [{ r: 22, g: 33, b: 62 }],
    [{ r: 0, g: 0, b: 0 }],
    [{ r: 255, g: 255, b: 255 }],
  ])('preserves %j within rounding', (rgb) => {
    const hsl = rgbToHsl(rgb);
    const back = hslToRgb(hsl);
    expect(Math.abs(back.r - rgb.r)).toBeLessThanOrEqual(1);
    expect(Math.abs(back.g - rgb.g)).toBeLessThanOrEqual(1);
    expect(Math.abs(back.b - rgb.b)).toBeLessThanOrEqual(1);
  });
});

describe('getReadableOnSurface', () => {
  const darkSurface = '#16213e';
  const lightSurface = '#ffffff';

  it('returns the original colour when contrast already meets the threshold', () => {
    // White on dark navy is well above 4.5:1.
    const fg = '#ffffff';
    expect(getReadableOnSurface(fg, darkSurface)).toBe(fg);
  });

  it('lifts the default indigo theme colour above the AA threshold on dark navy', () => {
    // Spot-checks the theme.ts TEAM_*_LIGHT / SERVE constants used by
    // TeamPanel — they fall just below 4.5:1 against --surface in dark
    // mode (~3.27:1) and the helper should rescue them.
    const adjusted = getReadableOnSurface('#5c6bc0', darkSurface);
    const ratio = contrastRatio(parseHexColor(adjusted)!, parseHexColor(darkSurface)!);
    expect(ratio).toBeGreaterThanOrEqual(4.5);
  });

  it('lifts a dark team colour against a dark surface to meet AA', () => {
    const fg = '#1a1f3a'; // close to the surface — invisible blob
    const adjusted = getReadableOnSurface(fg, darkSurface);
    const ratio = contrastRatio(parseHexColor(adjusted)!, parseHexColor(darkSurface)!);
    expect(ratio).toBeGreaterThanOrEqual(4.5);
  });

  it('lowers a light team colour against a light surface to meet AA', () => {
    const fg = '#fff2cc'; // pale yellow on white
    const adjusted = getReadableOnSurface(fg, lightSurface);
    const ratio = contrastRatio(parseHexColor(adjusted)!, parseHexColor(lightSurface)!);
    expect(ratio).toBeGreaterThanOrEqual(4.5);
  });

  it('preserves the original hue when shifting lightness', () => {
    const fg = '#1a1f3a';
    const adjusted = getReadableOnSurface(fg, darkSurface);
    const hueOrig = rgbToHsl(parseHexColor(fg)!).h;
    const hueAdj = rgbToHsl(parseHexColor(adjusted)!).h;
    // Allow small drift from rounding when L is near extremes.
    expect(Math.abs(hueAdj - hueOrig)).toBeLessThan(10);
  });

  it('honours a custom minimum ratio (e.g. 3:1 for non-text UI)', () => {
    const fg = '#15203c';
    const adjusted = getReadableOnSurface(fg, darkSurface, 3);
    const ratio = contrastRatio(parseHexColor(adjusted)!, parseHexColor(darkSurface)!);
    expect(ratio).toBeGreaterThanOrEqual(3);
  });

  it('returns the input unchanged when either colour is malformed', () => {
    expect(getReadableOnSurface('not-a-color', darkSurface)).toBe('not-a-color');
    expect(getReadableOnSurface('#123456', 'nope')).toBe('#123456');
  });
});

describe('rgbToHex', () => {
  it('clamps and pads channels', () => {
    expect(rgbToHex({ r: 0, g: 0, b: 0 })).toBe('#000000');
    expect(rgbToHex({ r: 255, g: 255, b: 255 })).toBe('#ffffff');
    expect(rgbToHex({ r: 300, g: -5, b: 16 })).toBe('#ff0010');
  });
});
