import { describe, it, expect, vi } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import { renderWithI18n } from './helpers';
import MatchCalendar, { dayKey } from '../components/MatchCalendar';

// A fixed local day: 2026-03-15 12:00 local → unix seconds.
const MAR_15 = Math.floor(new Date(2026, 2, 15, 12, 0, 0).getTime() / 1000);
const MAR_20 = Math.floor(new Date(2026, 2, 20, 12, 0, 0).getTime() / 1000);

describe('MatchCalendar', () => {
  it('derives a local day key from a unix timestamp', () => {
    expect(dayKey(MAR_15)).toBe('2026-03-15');
  });

  it('opens to the most recent match month and marks match days as clickable', () => {
    renderWithI18n(
      <MatchCalendar matchTimes={[MAR_15, MAR_20]} selected={null} onSelect={vi.fn()} />,
    );
    fireEvent.click(screen.getByRole('button', { name: /filter by day/i }));
    // Day 15 has a match → enabled; day 10 has none → disabled.
    expect(screen.getByRole('button', { name: '15' })).toBeEnabled();
    expect(screen.getByRole('button', { name: '20' })).toBeEnabled();
    expect(screen.getByRole('button', { name: '10' })).toBeDisabled();
  });

  it('emits the picked day and closes the popover', () => {
    const onSelect = vi.fn();
    renderWithI18n(
      <MatchCalendar matchTimes={[MAR_15, MAR_20]} selected={null} onSelect={onSelect} />,
    );
    fireEvent.click(screen.getByRole('button', { name: /filter by day/i }));
    fireEvent.click(screen.getByRole('button', { name: '20' }));
    expect(onSelect).toHaveBeenCalledWith('2026-03-20');
    // Popover closed: the grid day buttons are gone.
    expect(screen.queryByRole('button', { name: '15' })).toBeNull();
  });

  it('shows a clear ("all days") affordance only when a day is selected', () => {
    const onSelect = vi.fn();
    const { rerender, container } = renderWithI18n(
      <MatchCalendar matchTimes={[MAR_15]} selected={null} onSelect={onSelect} />,
    );
    expect(screen.queryByRole('button', { name: /all days/i })).toBeNull();
    rerender(<MatchCalendar matchTimes={[MAR_15]} selected="2026-03-15" onSelect={onSelect} />);
    fireEvent.click(screen.getByRole('button', { name: /all days/i }));
    expect(onSelect).toHaveBeenCalledWith(null);
    expect(container).toBeTruthy();
  });
});
