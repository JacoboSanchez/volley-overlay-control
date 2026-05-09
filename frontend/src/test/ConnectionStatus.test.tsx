import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { act, screen } from '@testing-library/react';
import ConnectionStatus from '../components/ConnectionStatus';
import { I18nProvider } from '../i18n';
import { SettingsProvider } from '../hooks/useSettings';
import { renderWithI18n } from './helpers';

describe('ConnectionStatus', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('does not surface a visible pill while connected', () => {
    renderWithI18n(<ConnectionStatus connected={true} />);
    expect(screen.queryByTestId('connection-status')).toBeNull();
  });

  it('keeps the offline pill hidden during the grace window', () => {
    renderWithI18n(<ConnectionStatus connected={false} graceMs={500} />);
    expect(screen.queryByTestId('connection-status')).toBeNull();
    act(() => { vi.advanceTimersByTime(400); });
    expect(screen.queryByTestId('connection-status')).toBeNull();
  });

  it('shows the offline pill once the grace window elapses', () => {
    renderWithI18n(<ConnectionStatus connected={false} graceMs={500} />);
    act(() => { vi.advanceTimersByTime(600); });
    const pill = screen.getByTestId('connection-status');
    expect(pill).toBeInTheDocument();
    expect(pill).toHaveTextContent('Reconnecting…');
    expect(pill.getAttribute('role')).toBe('status');
    expect(pill.getAttribute('aria-live')).toBe('polite');
  });

  it('hides the offline pill again as soon as the link recovers', () => {
    const { rerender } = renderWithI18n(
      <ConnectionStatus connected={false} graceMs={500} />,
    );
    act(() => { vi.advanceTimersByTime(600); });
    expect(screen.getByTestId('connection-status')).toBeInTheDocument();
    rerender(
      <I18nProvider>
        <SettingsProvider>
          <ConnectionStatus connected={true} graceMs={500} />
        </SettingsProvider>
      </I18nProvider>,
    );
    expect(screen.queryByTestId('connection-status')).toBeNull();
  });
});
