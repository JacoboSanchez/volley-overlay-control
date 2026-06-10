import { describe, it, expect, vi } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import SetSummaryActiveNotice from '../components/SetSummaryActiveNotice';
import { renderWithI18n } from './helpers';

describe('SetSummaryActiveNotice', () => {
  it('announces which set is on air', () => {
    renderWithI18n(
      <SetSummaryActiveNotice
        setNum={2}
        style="brand_ledger"
        onDeactivate={() => {}}
        onChangeStyle={() => {}}
      />,
    );
    expect(screen.getByTestId('set-summary-notice')).toHaveTextContent(
      'Showing set 2 on the overlay.',
    );
  });

  it('falls back to a dash when the set number is missing or zero', () => {
    const { unmount } = renderWithI18n(
      <SetSummaryActiveNotice
        setNum={null}
        style="brand_ledger"
        onDeactivate={() => {}}
        onChangeStyle={() => {}}
      />,
    );
    expect(screen.getByTestId('set-summary-notice')).toHaveTextContent('Showing set –');
    unmount();
    renderWithI18n(
      <SetSummaryActiveNotice
        setNum={0}
        style="brand_ledger"
        onDeactivate={() => {}}
        onChangeStyle={() => {}}
      />,
    );
    expect(screen.getByTestId('set-summary-notice')).toHaveTextContent('Showing set –');
  });

  it('fires onDeactivate from the hide button', () => {
    const onDeactivate = vi.fn();
    renderWithI18n(
      <SetSummaryActiveNotice
        setNum={1}
        style="brand_ledger"
        onDeactivate={onDeactivate}
        onChangeStyle={() => {}}
      />,
    );
    fireEvent.click(screen.getByTestId('set-summary-notice-deactivate'));
    expect(onDeactivate).toHaveBeenCalledOnce();
  });

  it('embeds the style picker and forwards style changes', () => {
    const onChangeStyle = vi.fn();
    renderWithI18n(
      <SetSummaryActiveNotice
        setNum={1}
        style="brand_ledger"
        onDeactivate={() => {}}
        onChangeStyle={onChangeStyle}
      />,
    );
    fireEvent.click(screen.getByTestId('set-summary-style-glass'));
    expect(onChangeStyle).toHaveBeenCalledWith('glass');
  });

  it('disables the toggle and picker while busy', () => {
    const onDeactivate = vi.fn();
    const onChangeStyle = vi.fn();
    renderWithI18n(
      <SetSummaryActiveNotice
        setNum={1}
        style="brand_ledger"
        busy
        onDeactivate={onDeactivate}
        onChangeStyle={onChangeStyle}
      />,
    );
    const hide = screen.getByTestId('set-summary-notice-deactivate');
    expect(hide).toBeDisabled();
    fireEvent.click(hide);
    expect(onDeactivate).not.toHaveBeenCalled();
    const option = screen.getByTestId('set-summary-style-glass');
    expect(option).toBeDisabled();
    fireEvent.click(option);
    expect(onChangeStyle).not.toHaveBeenCalled();
  });
});
