import { describe, it, expect } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithI18n } from './helpers';
import SideSwitchIndicator from '../components/SideSwitchIndicator';

describe('SideSwitchIndicator', () => {
  it('renders nothing for indoor (info=null)', () => {
    renderWithI18n(<SideSwitchIndicator info={null} />);
    expect(screen.queryByTestId('side-switch-indicator')).toBeNull();
  });

  it('renders the "in N points" form when not pending', () => {
    renderWithI18n(
      <SideSwitchIndicator
        info={{
          interval: 7,
          points_in_set: 5,
          next_switch_at: 7,
          points_until_switch: 2,
          is_switch_pending: false,
        }}
      />,
    );
    const el = screen.getByTestId('side-switch-indicator');
    expect(el.textContent).toMatch(/2/);
    expect(el.className).not.toMatch(/pending/);
  });

  it('renders the pending form on a boundary point', () => {
    renderWithI18n(
      <SideSwitchIndicator
        info={{
          interval: 7,
          points_in_set: 7,
          next_switch_at: 14,
          points_until_switch: 7,
          is_switch_pending: true,
        }}
      />,
    );
    const el = screen.getByTestId('side-switch-indicator');
    expect(el.className).toMatch(/pending/);
    expect(el.getAttribute('aria-live')).toBe('polite');
  });
});
