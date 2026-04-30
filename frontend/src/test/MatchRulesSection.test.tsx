import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { renderWithI18n } from './helpers';
import MatchRulesSection from '../components/config/MatchRulesSection';
import * as api from '../api/client';

vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client');
  return {
    ...actual,
    setRules: vi.fn().mockResolvedValue({ success: true, state: null }),
  };
});

const mockedSetRules = vi.mocked(api.setRules);

beforeEach(() => {
  mockedSetRules.mockClear();
});

describe('MatchRulesSection', () => {
  it('shows a loading placeholder until live config arrives', () => {
    renderWithI18n(
      <MatchRulesSection
        oid="oid"
        mode={null}
        pointsLimit={null}
        pointsLimitLastSet={null}
        setsLimit={null}
      />,
    );
    expect(screen.queryByTestId('rules-mode-toggle')).toBeNull();
  });

  it('marks the active mode as checked', () => {
    renderWithI18n(
      <MatchRulesSection oid="oid" mode="beach"
        pointsLimit={21} pointsLimitLastSet={15} setsLimit={3} />,
    );
    const indoor = screen.getByTestId('rules-mode-indoor');
    const beach = screen.getByTestId('rules-mode-beach');
    expect(indoor.getAttribute('aria-checked')).toBe('false');
    expect(beach.getAttribute('aria-checked')).toBe('true');
  });

  it('changing mode posts reset_to_defaults=true', async () => {
    renderWithI18n(
      <MatchRulesSection oid="my-oid" mode="indoor"
        pointsLimit={25} pointsLimitLastSet={15} setsLimit={5} />,
    );
    fireEvent.click(screen.getByTestId('rules-mode-beach'));
    await waitFor(() => expect(mockedSetRules).toHaveBeenCalled());
    expect(mockedSetRules).toHaveBeenCalledWith('my-oid', {
      mode: 'beach', reset_to_defaults: true,
    });
  });

  it('changing the sets selector posts only sets_limit', async () => {
    renderWithI18n(
      <MatchRulesSection oid="my-oid" mode="indoor"
        pointsLimit={25} pointsLimitLastSet={15} setsLimit={5} />,
    );
    const sel = screen.getByTestId('rules-sets-select') as HTMLSelectElement;
    fireEvent.change(sel, { target: { value: '3' } });
    await waitFor(() => expect(mockedSetRules).toHaveBeenCalled());
    expect(mockedSetRules).toHaveBeenCalledWith('my-oid', { sets_limit: 3 });
  });

  it('committing the points input posts points_limit on blur', async () => {
    renderWithI18n(
      <MatchRulesSection oid="my-oid" mode="indoor"
        pointsLimit={25} pointsLimitLastSet={15} setsLimit={5} />,
    );
    const input = screen.getByTestId('rules-points-input') as HTMLInputElement;
    fireEvent.change(input, { target: { value: '27' } });
    fireEvent.blur(input);
    await waitFor(() => expect(mockedSetRules).toHaveBeenCalled());
    expect(mockedSetRules).toHaveBeenCalledWith('my-oid', { points_limit: 27 });
  });

  it('reset-to-defaults button is disabled when already at preset', () => {
    renderWithI18n(
      <MatchRulesSection oid="my-oid" mode="indoor"
        pointsLimit={25} pointsLimitLastSet={15} setsLimit={5} />,
    );
    const btn = screen.getByTestId('rules-reset-defaults') as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it('reset-to-defaults posts mode + reset flag when limits diverge', async () => {
    renderWithI18n(
      <MatchRulesSection oid="my-oid" mode="indoor"
        pointsLimit={27} pointsLimitLastSet={15} setsLimit={5} />,
    );
    const btn = screen.getByTestId('rules-reset-defaults');
    fireEvent.click(btn);
    await waitFor(() => expect(mockedSetRules).toHaveBeenCalled());
    expect(mockedSetRules).toHaveBeenCalledWith('my-oid', {
      mode: 'indoor', reset_to_defaults: true,
    });
  });
});
