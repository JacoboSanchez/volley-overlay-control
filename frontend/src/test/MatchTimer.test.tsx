import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithI18n } from './helpers';
import MatchTimer from '../components/MatchTimer';

describe('MatchTimer', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders nothing when startedAt is null', () => {
    renderWithI18n(<MatchTimer startedAt={null} />);
    expect(screen.queryByTestId('match-timer')).toBeNull();
  });

  it('renders nothing when startedAt is undefined', () => {
    renderWithI18n(<MatchTimer startedAt={undefined} />);
    expect(screen.queryByTestId('match-timer')).toBeNull();
  });

  it('renders 0:00 immediately after the start', () => {
    const now = 1_700_000_000_000; // ms
    vi.setSystemTime(new Date(now));
    renderWithI18n(<MatchTimer startedAt={now / 1000} />);
    expect(screen.getByTestId('match-timer')).toHaveTextContent('0:00');
  });

  it('renders M:SS in tabular form (zero-padded seconds)', () => {
    const start = 1_700_000_000;
    vi.setSystemTime(new Date(start * 1000 + 9_000));
    renderWithI18n(<MatchTimer startedAt={start} />);
    expect(screen.getByTestId('match-timer')).toHaveTextContent('0:09');
  });

  it('formats minutes correctly past 60 s', () => {
    const start = 1_700_000_000;
    vi.setSystemTime(new Date(start * 1000 + 125_000));
    renderWithI18n(<MatchTimer startedAt={start} />);
    expect(screen.getByTestId('match-timer')).toHaveTextContent('2:05');
  });

  it('clamps to 0:00 when start is in the future (clock skew)', () => {
    const now = 1_700_000_000_000;
    vi.setSystemTime(new Date(now));
    renderWithI18n(<MatchTimer startedAt={now / 1000 + 30} />);
    expect(screen.getByTestId('match-timer')).toHaveTextContent('0:00');
  });
});
