import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import ActionChip from '../components/ActionChip';
import { CHIP_CATALOGUE, classifyChip } from '../utils/chipCatalogue';

describe('ActionChip', () => {
  it('renders the team-1 point chip with the expected glyph and class', () => {
    render(<ActionChip kind="point-t1" />);
    const chip = screen.getByTestId('action-chip');
    expect(chip).toHaveAttribute('data-kind', 'point-t1');
    expect(chip.className).toContain('action-chip-point-t1');
    expect(chip.querySelector('.chip-glyph-point-t1')).not.toBeNull();
    expect(chip).toHaveTextContent(CHIP_CATALOGUE['point-t1'].glyph);
  });

  it('classifies action+team when kind is omitted', () => {
    render(<ActionChip action="add_point" team={2} />);
    const chip = screen.getByTestId('action-chip');
    expect(chip).toHaveAttribute('data-kind', 'point-t2');
  });

  it('falls back to undone when wasUndone and no specific action match', () => {
    // ``add_point`` always wins over the wasUndone branch, so use a
    // truly unmatched action to land on the wasUndone fallback.
    render(<ActionChip action="weird_event" wasUndone />);
    const chip = screen.getByTestId('action-chip');
    expect(chip).toHaveAttribute('data-kind', 'undone');
  });

  it('falls back to other for unrecognised actions without wasUndone', () => {
    render(<ActionChip action="rocket_launch" />);
    expect(screen.getByTestId('action-chip')).toHaveAttribute('data-kind', 'other');
  });

  it('hides the label when glyphOnly is true', () => {
    render(<ActionChip kind="set" label="Set won" glyphOnly />);
    const chip = screen.getByTestId('action-chip');
    expect(chip.querySelector('.action-chip-label')).toBeNull();
  });

  it('renders the label alongside the glyph when not glyphOnly', () => {
    render(<ActionChip kind="set" label="Set won" />);
    expect(screen.getByText('Set won')).toBeInTheDocument();
  });

  it('classifyChip helper maps the documented action set', () => {
    expect(classifyChip('add_point', 1, false)).toBe('point-t1');
    expect(classifyChip('add_point', 2, false)).toBe('point-t2');
    expect(classifyChip('add_point', undefined, false)).toBe('point');
    expect(classifyChip('add_set', 1, false)).toBe('set');
    expect(classifyChip('add_timeout', 2, false)).toBe('timeout');
    expect(classifyChip('change_serve', 1, false)).toBe('serve');
    expect(classifyChip('set_score', 1, false)).toBe('edit');
    expect(classifyChip('reset', undefined, false)).toBe('reset');
    expect(classifyChip('mystery', undefined, true)).toBe('undone');
    expect(classifyChip('mystery', undefined, false)).toBe('other');
  });
});
