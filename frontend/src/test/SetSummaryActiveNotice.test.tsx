import { describe, it, expect, vi } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import SetSummaryActiveNotice from '../components/SetSummaryActiveNotice';
import { renderWithI18n } from './helpers';

describe('SetSummaryActiveNotice', () => {
  it('shows only the hide button by default (the preview carries the status)', () => {
    renderWithI18n(<SetSummaryActiveNotice setNum={2} onDeactivate={() => {}} />);
    expect(screen.getByTestId('set-summary-notice-deactivate')).toHaveTextContent('Hide summary');
    expect(screen.queryByTestId('set-summary-notice-status')).not.toBeInTheDocument();
    expect(screen.queryByTestId('set-summary-style-picker')).not.toBeInTheDocument();
  });

  it('announces which set is on air when asked to show the status', () => {
    renderWithI18n(<SetSummaryActiveNotice setNum={2} showStatus onDeactivate={() => {}} />);
    expect(screen.getByTestId('set-summary-notice-status')).toHaveTextContent(
      'Showing set 2 on the overlay.',
    );
  });

  it('falls back to a dash when the set number is missing or zero', () => {
    const { unmount } = renderWithI18n(
      <SetSummaryActiveNotice setNum={null} showStatus onDeactivate={() => {}} />,
    );
    expect(screen.getByTestId('set-summary-notice-status')).toHaveTextContent('Showing set –');
    unmount();
    renderWithI18n(<SetSummaryActiveNotice setNum={0} showStatus onDeactivate={() => {}} />);
    expect(screen.getByTestId('set-summary-notice-status')).toHaveTextContent('Showing set –');
  });

  it('applies the inline modifier for the alerts-row placement', () => {
    renderWithI18n(<SetSummaryActiveNotice setNum={1} inline onDeactivate={() => {}} />);
    expect(screen.getByTestId('set-summary-notice')).toHaveClass('set-summary-notice-inline');
  });

  it('fires onDeactivate from the hide button', () => {
    const onDeactivate = vi.fn();
    renderWithI18n(<SetSummaryActiveNotice setNum={1} onDeactivate={onDeactivate} />);
    fireEvent.click(screen.getByTestId('set-summary-notice-deactivate'));
    expect(onDeactivate).toHaveBeenCalledOnce();
  });

  it('disables the hide button while busy', () => {
    const onDeactivate = vi.fn();
    renderWithI18n(<SetSummaryActiveNotice setNum={1} busy onDeactivate={onDeactivate} />);
    const hide = screen.getByTestId('set-summary-notice-deactivate');
    expect(hide).toBeDisabled();
    fireEvent.click(hide);
    expect(onDeactivate).not.toHaveBeenCalled();
  });
});
