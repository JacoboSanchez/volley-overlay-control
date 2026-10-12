import { describe, it, expect, vi } from 'vitest';
import { fireEvent, screen } from '@testing-library/react';
import RecapSection from '../components/config/RecapSection';
import { renderWithI18n } from './helpers';

const SETTINGS = {
  setSummaryEnabled: true,
  autoShowSetSummary: false,
  autoShowSetSummaryDelay: 3,
  autoShowSetSummaryDuration: 15,
};

describe('RecapSection theme selector', () => {
  it('is hidden unless a theme handler is provided', () => {
    renderWithI18n(<RecapSection settings={SETTINGS} setSetting={vi.fn()} />);
    expect(screen.queryByTestId('set-summary-theme-selector')).not.toBeInTheDocument();
  });

  it('reports the chosen theme', () => {
    const onChange = vi.fn();
    renderWithI18n(
      <RecapSection
        settings={SETTINGS}
        setSetting={vi.fn()}
        overlayTheme=""
        onChangeOverlayTheme={onChange}
      />,
    );
    fireEvent.change(screen.getByTestId('set-summary-theme-selector'), {
      target: { value: 'light' },
    });
    expect(onChange).toHaveBeenCalledWith('light');
  });
});
