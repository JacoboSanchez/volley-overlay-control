import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import PointsHistoryStrip from '../components/PointsHistoryStrip';
import type { RecentEvent } from '../hooks/useRecentEvents';

const COMMON = {
  team1Color: '#1a73e8',
  team1TextColor: '#ffffff',
  team2Color: '#d93025',
  team2TextColor: '#000000',
  team1Name: 'Home',
  team2Name: 'Away',
};

function strip(events: RecentEvent[], opts: Partial<typeof COMMON> & {
  team1Logo?: string | null;
  team2Logo?: string | null;
} = {}) {
  return (
    <PointsHistoryStrip
      events={events}
      team1Color={opts.team1Color ?? COMMON.team1Color}
      team1TextColor={opts.team1TextColor ?? COMMON.team1TextColor}
      team1Logo={opts.team1Logo ?? null}
      team1Name={opts.team1Name ?? COMMON.team1Name}
      team2Color={opts.team2Color ?? COMMON.team2Color}
      team2TextColor={opts.team2TextColor ?? COMMON.team2TextColor}
      team2Logo={opts.team2Logo ?? null}
      team2Name={opts.team2Name ?? COMMON.team2Name}
    />
  );
}

describe('PointsHistoryStrip', () => {
  it('renders nothing when events array is empty', () => {
    const { container } = render(strip([]));
    expect(container.innerHTML).toBe('');
  });

  it('renders two rows, one per team, each with its marker', () => {
    render(strip([{ ts: 1, team: 1, kind: 'point_add' }]));
    expect(screen.getByTestId('phs-row-1')).toBeInTheDocument();
    expect(screen.getByTestId('phs-row-2')).toBeInTheDocument();
  });

  it('renders the chip in the team-1 row only when the event is for team 1', () => {
    render(
      strip([
        { ts: 1, team: 1, kind: 'point_add' },
        { ts: 2, team: 2, kind: 'point_add' },
      ]),
    );
    expect(screen.getByTestId('phs-chip-1-0')).toHaveTextContent('+1');
    expect(screen.queryByTestId('phs-chip-2-0')).not.toBeInTheDocument();
    expect(screen.getByTestId('phs-chip-2-1')).toHaveTextContent('+1');
    expect(screen.queryByTestId('phs-chip-1-1')).not.toBeInTheDocument();
  });

  it('renders point_undo as -1 (using a true minus sign)', () => {
    render(strip([{ ts: 1, team: 1, kind: 'point_undo' }]));
    expect(screen.getByTestId('phs-chip-1-0')).toHaveTextContent('−1');
  });

  it('renders manual chips with the absolute value (no sign)', () => {
    render(
      strip([
        { ts: 1, team: 1, kind: 'manual', value: 15 },
        { ts: 2, team: 2, kind: 'manual', value: 0 },
      ]),
    );
    expect(screen.getByTestId('phs-chip-1-0')).toHaveTextContent('15');
    expect(screen.getByTestId('phs-chip-2-1')).toHaveTextContent('0');
  });

  it('paints chip bg/fg from the team colour props', () => {
    render(
      strip([
        { ts: 1, team: 1, kind: 'point_add' },
        { ts: 2, team: 2, kind: 'point_add' },
      ]),
    );
    expect(screen.getByTestId('phs-chip-1-0')).toHaveStyle({
      backgroundColor: COMMON.team1Color,
      color: COMMON.team1TextColor,
    });
    expect(screen.getByTestId('phs-chip-2-1')).toHaveStyle({
      backgroundColor: COMMON.team2Color,
      color: COMMON.team2TextColor,
    });
  });

  it('shows the team logo inside the marker when provided', () => {
    render(strip([{ ts: 1, team: 1, kind: 'point_add' }], { team1Logo: '/logo1.png' }));
    const row1 = screen.getByTestId('phs-row-1');
    const img = row1.querySelector('img.phs-marker-logo');
    expect(img).not.toBeNull();
    expect(img).toHaveAttribute('src', '/logo1.png');
  });

  it('renders the marker without a logo when none is configured', () => {
    render(strip([{ ts: 1, team: 1, kind: 'point_add' }]));
    const row2 = screen.getByTestId('phs-row-2');
    expect(row2.querySelector('img.phs-marker-logo')).toBeNull();
  });

  it('uses the team name in chip aria-labels for accessibility', () => {
    render(strip([{ ts: 1, team: 1, kind: 'set_won' }]));
    expect(screen.getByTestId('phs-chip-1-0')).toHaveAttribute(
      'aria-label',
      'Home: set won',
    );
  });

  it('renders an SVG icon for set_won, timeout, timeout_undo and manual chips', () => {
    render(
      strip([
        { ts: 1, team: 1, kind: 'set_won' },
        { ts: 2, team: 2, kind: 'timeout' },
        { ts: 3, team: 1, kind: 'timeout_undo' },
        { ts: 4, team: 2, kind: 'manual', value: 4 },
      ]),
    );
    expect(screen.getByTestId('phs-chip-1-0').querySelector('svg')).not.toBeNull();
    expect(screen.getByTestId('phs-chip-2-1').querySelector('svg')).not.toBeNull();
    expect(screen.getByTestId('phs-chip-1-2').querySelector('svg')).not.toBeNull();
    expect(screen.getByTestId('phs-chip-2-3').querySelector('svg')).not.toBeNull();
  });
});
