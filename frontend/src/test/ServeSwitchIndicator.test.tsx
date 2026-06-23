import { describe, it, expect } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithI18n } from './helpers';
import ServeSwitchIndicator from '../components/ServeSwitchIndicator';

describe('ServeSwitchIndicator', () => {
  it('renders nothing for volleyball modes (info=null)', () => {
    renderWithI18n(<ServeSwitchIndicator info={null} />);
    expect(screen.queryByTestId('serve-switch-indicator')).toBeNull();
  });

  it('renders the "serve change in N" form when not pending', () => {
    renderWithI18n(
      <ServeSwitchIndicator
        info={{
          server: 1,
          points_in_set: 1,
          next_change_at: 2,
          points_until_change: 1,
          is_change_pending: false,
        }}
      />,
    );
    const el = screen.getByTestId('serve-switch-indicator');
    expect(el.textContent).toMatch(/1/);
    expect(el.className).not.toMatch(/pending/);
    expect(el.getAttribute('aria-live')).toBe('off');
  });

  it('renders the pending pill the moment serve changes', () => {
    renderWithI18n(
      <ServeSwitchIndicator
        info={{
          server: 2,
          points_in_set: 2,
          next_change_at: 4,
          points_until_change: 2,
          is_change_pending: true,
        }}
      />,
    );
    const el = screen.getByTestId('serve-switch-indicator');
    expect(el.className).toMatch(/pending/);
    expect(el.getAttribute('aria-live')).toBe('polite');
  });
});
