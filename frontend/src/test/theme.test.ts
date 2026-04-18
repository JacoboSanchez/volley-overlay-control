import { describe, it, expect } from 'vitest';
import {
  TEAM_A_COLOR,
  TEAM_B_COLOR,
  FONT_SCALES,
  FONT_OPTIONS,
} from '../theme';

describe('theme', () => {
  it('exports team colors as hex strings', () => {
    expect(TEAM_A_COLOR).toMatch(/^#[0-9a-f]{6}$/i);
    expect(TEAM_B_COLOR).toMatch(/^#[0-9a-f]{6}$/i);
  });

  it('FONT_OPTIONS matches FONT_SCALES keys', () => {
    expect(FONT_OPTIONS).toEqual(Object.keys(FONT_SCALES));
  });

  it('all font scales have scale and offset_y', () => {
    for (const [name, props] of Object.entries(FONT_SCALES)) {
      expect(props).toHaveProperty('scale');
      expect(props).toHaveProperty('offset_y');
      expect(typeof props.scale).toBe('number');
      expect(typeof props.offset_y).toBe('number');
    }
  });

  it('Default font has scale 1.0 and offset 0', () => {
    expect(FONT_SCALES.Default.scale).toBe(1.0);
    expect(FONT_SCALES.Default.offset_y).toBe(0.0);
  });
});
