import { describe, it, expect, vi } from 'vitest';
import { fireEvent, screen } from '@testing-library/react';
import { renderWithI18n } from './helpers';
import PositionSection from '../components/config/PositionSection';

describe('PositionSection', () => {
  it('renders the scale + margin inputs, defaulting when absent from the model', () => {
    renderWithI18n(<PositionSection model={{}} updateField={vi.fn()} />);

    // Scale defaults to 100%, margin to 0 when the model carries neither.
    expect(screen.getByTestId('scale-input')).toHaveValue(100);
    expect(screen.getByTestId('margin-input')).toHaveValue(0);
  });

  it('reflects model values and pushes edits through updateField', () => {
    const updateField = vi.fn();
    renderWithI18n(
      <PositionSection model={{ Scale: 110, Margin: -5 }} updateField={updateField} />,
    );

    expect(screen.getByTestId('scale-input')).toHaveValue(110);
    expect(screen.getByTestId('margin-input')).toHaveValue(-5);

    fireEvent.change(screen.getByTestId('scale-input'), { target: { value: '90' } });
    expect(updateField).toHaveBeenCalledWith('Scale', 90);

    fireEvent.change(screen.getByTestId('margin-input'), { target: { value: '7.5' } });
    expect(updateField).toHaveBeenCalledWith('Margin', 7.5);
  });

  it('picking an anchor zone sets Anchor and zeroes the nudge', () => {
    const updateField = vi.fn();
    renderWithI18n(<PositionSection model={{}} updateField={updateField} />);

    fireEvent.click(screen.getByTestId('anchor-top-right'));

    expect(updateField).toHaveBeenCalledWith('Anchor', 'top-right');
    // The legacy absolute defaults would read as a huge offset in zone
    // mode, so a freshly picked zone resets the fine nudge to 0.
    expect(updateField).toHaveBeenCalledWith('Left-Right', 0);
    expect(updateField).toHaveBeenCalledWith('Up-Down', 0);
  });

  it('relabels the H/V steppers as a nudge while a zone is active', () => {
    renderWithI18n(
      <PositionSection model={{ Anchor: 'bottom-left' }} updateField={vi.fn()} />,
    );

    // The active zone cell is pressed; the absolute "Free" mode is not.
    expect(screen.getByTestId('anchor-bottom-left')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTestId('anchor-free')).toHaveAttribute('aria-pressed', 'false');
    // H/V fields now read as a nudge rather than absolute coordinates.
    expect(screen.getByText('Nudge H')).toBeInTheDocument();
    expect(screen.getByText('Nudge V')).toBeInTheDocument();
  });

  it('defaults to Free mode with absolute H/V labels', () => {
    renderWithI18n(<PositionSection model={{}} updateField={vi.fn()} />);

    expect(screen.getByTestId('anchor-free')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText('H Pos')).toBeInTheDocument();
    expect(screen.getByText('V Pos')).toBeInTheDocument();
  });

  it('does not write a value when a position input is cleared (no NaN/null)', () => {
    const updateField = vi.fn();
    renderWithI18n(<PositionSection model={{ Scale: 120 }} updateField={updateField} />);

    fireEvent.change(screen.getByTestId('scale-input'), { target: { value: '' } });
    // Clearing yields NaN; writing it would persist null for the coordinate.
    expect(updateField).not.toHaveBeenCalled();

    fireEvent.change(screen.getByTestId('scale-input'), { target: { value: '90' } });
    expect(updateField).toHaveBeenCalledWith('Scale', 90);
  });

  it('restores absolute coordinate defaults when leaving zone mode', () => {
    const updateField = vi.fn();
    renderWithI18n(
      <PositionSection model={{ Anchor: 'top-right' }} updateField={updateField} />,
    );

    fireEvent.click(screen.getByTestId('anchor-free'));

    expect(updateField).toHaveBeenCalledWith('Anchor', 'free');
    // The 0/0 nudge would read as canvas-centre in free mode, so the absolute
    // defaults are restored instead.
    expect(updateField).toHaveBeenCalledWith('Left-Right', -33);
    expect(updateField).toHaveBeenCalledWith('Up-Down', -41.1);
  });

  it('reset-to-defaults stages the free anchor and every field default', () => {
    const updateField = vi.fn();
    renderWithI18n(
      <PositionSection
        model={{ Anchor: 'top-right', Height: 20, Width: 50, 'Left-Right': 5, 'Up-Down': 5 }}
        updateField={updateField}
      />,
    );
    const btn = screen.getByTestId('position-reset-defaults');
    expect(btn).not.toBeDisabled();
    fireEvent.click(btn);

    expect(updateField).toHaveBeenCalledWith('Anchor', 'free');
    expect(updateField).toHaveBeenCalledWith('Height', 10);
    expect(updateField).toHaveBeenCalledWith('Width', 30);
    expect(updateField).toHaveBeenCalledWith('Left-Right', -33);
    expect(updateField).toHaveBeenCalledWith('Up-Down', -41.1);
    expect(updateField).toHaveBeenCalledWith('Scale', 100);
    expect(updateField).toHaveBeenCalledWith('Margin', 0);
  });

  it('reset-to-defaults is disabled when everything is already at defaults', () => {
    renderWithI18n(
      <PositionSection
        model={{
          Anchor: 'free',
          Height: 10,
          Width: 30,
          'Left-Right': -33,
          'Up-Down': -41.1,
          Scale: 100,
          Margin: 0,
        }}
        updateField={vi.fn()}
      />,
    );
    expect(screen.getByTestId('position-reset-defaults')).toBeDisabled();
  });

  it('shows the units hint', () => {
    renderWithI18n(<PositionSection model={{}} updateField={vi.fn()} />);
    expect(screen.getByText('Values are a percentage of the overlay canvas')).toBeInTheDocument();
  });
});
