import { describe, it, expect, vi } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import PointTypePicker from '../components/PointTypePicker';
import { renderWithI18n } from './helpers';

function setup(extendedErrors: boolean, onPick = vi.fn(), onClose = vi.fn()) {
  renderWithI18n(
    <PointTypePicker
      team={1}
      teamName="Home"
      color="#0000ff"
      textColor="#ffffff"
      extendedErrors={extendedErrors}
      onPick={onPick}
      onClose={onClose}
    />,
  );
  return { onPick, onClose };
}

describe('PointTypePicker', () => {
  it('scores a tagged point on a type choice', () => {
    const { onPick } = setup(false);
    fireEvent.click(screen.getByTestId('point-picker-ace'));
    expect(onPick).toHaveBeenCalledWith('ace');
  });

  it('"Quick point" scores untyped', () => {
    const { onPick } = setup(false);
    fireEvent.click(screen.getByTestId('point-picker-quick'));
    // No point type → untyped point (no args).
    expect(onPick).toHaveBeenCalledWith();
  });

  it('sends opp_error directly when extended errors are off', () => {
    const { onPick } = setup(false);
    fireEvent.click(screen.getByTestId('point-picker-opp_error'));
    expect(onPick).toHaveBeenCalledWith('opp_error');
    // No second step shown.
    expect(screen.queryByTestId('point-picker-error-serve_error')).toBeNull();
  });

  it('opens the error-cause step when extended errors are on', () => {
    const { onPick } = setup(true);
    fireEvent.click(screen.getByTestId('point-picker-opp_error'));
    // The main step did not score yet — it revealed the cause picker.
    expect(onPick).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId('point-picker-error-serve_error'));
    expect(onPick).toHaveBeenCalledWith('opp_error', 'serve_error');
  });

  it('"Other" covers the no-specific-cause case', () => {
    const { onPick } = setup(true);
    fireEvent.click(screen.getByTestId('point-picker-opp_error'));
    // The generic-error button was removed; "Other" is the catch-all.
    expect(screen.queryByTestId('point-picker-error-generic')).toBeNull();
    fireEvent.click(screen.getByTestId('point-picker-error-other'));
    expect(onPick).toHaveBeenCalledWith('opp_error', 'other');
  });
});
