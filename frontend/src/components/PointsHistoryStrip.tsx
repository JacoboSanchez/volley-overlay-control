import type { RecentPoint } from '../hooks/useRecentPoints';

export interface PointsHistoryStripProps {
  points: RecentPoint[];
  /** Background colour for team 1 chips. Same value the score buttons use. */
  team1Color: string;
  /** Foreground (letter) colour for team 1 chips. */
  team1TextColor: string;
  /** Background colour for team 2 chips. Same value the score buttons use. */
  team2Color: string;
  /** Foreground (letter) colour for team 2 chips. */
  team2TextColor: string;
}

export default function PointsHistoryStrip({
  points,
  team1Color,
  team1TextColor,
  team2Color,
  team2TextColor,
}: PointsHistoryStripProps) {
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
          style={{
            backgroundColor: p.team === 1 ? team1Color : team2Color,
            color: p.team === 1 ? team1TextColor : team2TextColor,
          }}
        >
          {p.team === 1 ? 'A' : 'B'}
        </span>
      ))}
    </div>
  );
}
