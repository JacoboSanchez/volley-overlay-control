import type { RecentPoint } from '../hooks/useRecentPoints';
import { TEAM_A_COLOR, TEAM_B_COLOR } from '../theme';

export interface PointsHistoryStripProps {
  points: RecentPoint[];
}

export default function PointsHistoryStrip({ points }: PointsHistoryStripProps) {
  if (points.length === 0) return null;
  return (
    <div
      className="points-history-strip"
      data-testid="points-history-strip"
      aria-label="Last points"
    >
      {points.map((p, i) => (
        <span
          key={`${p.ts}-${i}`}
          className={`points-history-chip points-history-chip-team-${p.team}`}
          data-testid={`points-history-chip-${i}`}
          style={{ backgroundColor: p.team === 1 ? TEAM_A_COLOR : TEAM_B_COLOR }}
        >
          {p.team === 1 ? 'A' : 'B'}
        </span>
      ))}
    </div>
  );
}
