import { describe, it, expect, vi } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import SetSummaryStylePicker from '../components/SetSummaryStylePicker';
import { SET_SUMMARY_STYLES } from '../api/client';
import { renderWithI18n } from './helpers';

describe('SetSummaryStylePicker', () => {
  it('renders one radio per style inside a labelled radiogroup', () => {
    renderWithI18n(<SetSummaryStylePicker value="brand_ledger" onChange={() => {}} />);
    expect(screen.getByRole('radiogroup')).toBeInTheDocument();
    const radios = screen.getAllByRole('radio');
    expect(radios).toHaveLength(SET_SUMMARY_STYLES.length);
    for (const style of SET_SUMMARY_STYLES) {
      expect(screen.getByTestId(`set-summary-style-${style}`)).toBeInTheDocument();
    }
  });

  it('marks only the current value as checked', () => {
    renderWithI18n(<SetSummaryStylePicker value="podium" onChange={() => {}} />);
    expect(screen.getByTestId('set-summary-style-podium')).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByTestId('set-summary-style-podium').className).toContain('selected');
    const checked = screen
      .getAllByRole('radio')
      .filter((el) => el.getAttribute('aria-checked') === 'true');
    expect(checked).toHaveLength(1);
  });

  it('fires onChange with the picked style', () => {
    const onChange = vi.fn();
    renderWithI18n(<SetSummaryStylePicker value="brand_ledger" onChange={onChange} />);
    fireEvent.click(screen.getByTestId('set-summary-style-bento'));
    expect(onChange).toHaveBeenCalledOnce();
    expect(onChange).toHaveBeenCalledWith('bento');
  });

  it('does not refire when the already-selected style is clicked', () => {
    const onChange = vi.fn();
    renderWithI18n(<SetSummaryStylePicker value="bento" onChange={onChange} />);
    fireEvent.click(screen.getByTestId('set-summary-style-bento'));
    expect(onChange).not.toHaveBeenCalled();
  });

  it('disables every option and suppresses onChange when disabled', () => {
    const onChange = vi.fn();
    renderWithI18n(<SetSummaryStylePicker value="bento" onChange={onChange} disabled />);
    for (const radio of screen.getAllByRole('radio')) {
      expect(radio).toBeDisabled();
    }
    fireEvent.click(screen.getByTestId('set-summary-style-glass'));
    expect(onChange).not.toHaveBeenCalled();
  });
});
