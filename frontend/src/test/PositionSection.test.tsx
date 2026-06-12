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
});
