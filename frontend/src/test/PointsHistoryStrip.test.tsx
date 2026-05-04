import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import PointsHistoryStrip from '../components/PointsHistoryStrip';
import type { RecentPoint } from '../hooks/useRecentPoints';
import { TEAM_A_COLOR, TEAM_B_COLOR } from '../theme';

describe('PointsHistoryStrip', () => {
  it('renders nothing when points array is empty', () => {
    const { container } = render(<PointsHistoryStrip points={[]} />);
    expect(container.innerHTML).toBe('');
  });

  it('renders one chip per point in the order given', () => {
    const points: RecentPoint[] = [
      { team: 1, ts: 1 },
      { team: 2, ts: 2 },
      { team: 1, ts: 3 },
    ];
    render(<PointsHistoryStrip points={points} />);
    const chips = [
      screen.getByTestId('points-history-chip-0'),
      screen.getByTestId('points-history-chip-1'),
      screen.getByTestId('points-history-chip-2'),
    ];
    expect(chips[0]).toHaveTextContent('A');
    expect(chips[1]).toHaveTextContent('B');
    expect(chips[2]).toHaveTextContent('A');
  });

  it('applies team-specific class and inline color', () => {
    const points: RecentPoint[] = [
      { team: 1, ts: 1 },
      { team: 2, ts: 2 },
    ];
    render(<PointsHistoryStrip points={points} />);
    const chip1 = screen.getByTestId('points-history-chip-0');
    const chip2 = screen.getByTestId('points-history-chip-1');
    expect(chip1).toHaveClass('points-history-chip-team-1');
    expect(chip2).toHaveClass('points-history-chip-team-2');
    expect(chip1).toHaveStyle({ backgroundColor: TEAM_A_COLOR });
    expect(chip2).toHaveStyle({ backgroundColor: TEAM_B_COLOR });
  });

  it('renders the strip container with an aria-label for accessibility', () => {
    const points: RecentPoint[] = [{ team: 1, ts: 1 }];
    render(<PointsHistoryStrip points={points} />);
    const strip = screen.getByTestId('points-history-strip');
    expect(strip).toHaveAttribute('aria-label', 'Last points');
  });
});
