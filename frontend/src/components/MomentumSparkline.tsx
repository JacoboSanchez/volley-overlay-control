import { useMemo } from 'react';
import type { LiveStatsPoint } from '../api/client';

export interface MomentumSparklineProps {
  history: LiveStatsPoint[];
  /** Width of the SVG in pixels. */
  width?: number;
  /** Height of the SVG in pixels. */
  height?: number;
  /** Hex / CSS colour for the home (team 1) area. */
  colorTeam1?: string;
  /** Hex / CSS colour for the away (team 2) area. */
  colorTeam2?: string;
  /** Optional accessible label override. */
  ariaLabel?: string;
}

interface Point {
  x: number;
  y: number;
  diff: number;
}

const PAD_X = 2;
const PAD_Y = 4;

function computePoints(
  history: LiveStatsPoint[],
  width: number,
  height: number,
): { pts: Point[]; maxDiff: number } {
  if (history.length === 0) return { pts: [], maxDiff: 1 };
  // Diff = team1.score - team2.score after each scoring event.
  // Each entry already carries the post-action running score, so we
  // just project that diff into the SVG plot box.
  const diffs = history.map((h) => h.score[0] - h.score[1]);
  const maxAbs = Math.max(1, ...diffs.map((d) => Math.abs(d)));
  const innerW = Math.max(1, width - PAD_X * 2);
  const innerH = Math.max(1, height - PAD_Y * 2);
  const step = history.length > 1 ? innerW / (history.length - 1) : 0;
  const pts: Point[] = diffs.map((d, i) => {
    const x = PAD_X + step * i;
    // Diff = 0 plots on the horizontal mid-line; positive (T1 leading)
    // climbs up, negative (T2 leading) drops down.
    const y = PAD_Y + innerH / 2 - (d / maxAbs) * (innerH / 2);
    return { x, y, diff: d };
  });
  return { pts, maxDiff: maxAbs };
}

function polylinePath(pts: Point[]): string {
  if (pts.length === 0) return '';
  return pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(2)},${p.y.toFixed(2)}`).join(' ');
}

function areaPath(
  pts: Point[],
  midY: number,
  side: 'above' | 'below',
): string {
  if (pts.length === 0) return '';
  // Fill the polygon between the polyline and the mid-line. We only
  // render the side where the diff sign matches; the SVG clipPath
  // does the actual masking via the mid-line.
  const filtered = pts.map((p) => ({
    x: p.x,
    y: side === 'above' ? Math.min(p.y, midY) : Math.max(p.y, midY),
  }));
  const first = filtered[0]!;
  const last = filtered[filtered.length - 1]!;
  const start = `M${first.x.toFixed(2)},${midY.toFixed(2)}`;
  const line = filtered
    .map((p) => `L${p.x.toFixed(2)},${p.y.toFixed(2)}`)
    .join(' ');
  const close = ` L${last.x.toFixed(2)},${midY.toFixed(2)} Z`;
  return `${start} ${line}${close}`;
}

/**
 * Compact area chart visualising the point differential over time.
 *
 * The plot box is split horizontally: the team-1 colour fills the
 * area above the centre line whenever team 1 is leading after a point;
 * team-2 fills below. Diff = 0 hugs the centre. The result reads
 * "who has the momentum" at a glance without numeric labels.
 *
 * Renders nothing when the history is empty so the parent can collapse
 * the slot. No external dependencies; one inline SVG.
 */
export default function MomentumSparkline({
  history,
  width = 220,
  height = 48,
  colorTeam1 = '#E21836',
  colorTeam2 = '#0047AB',
  ariaLabel,
}: MomentumSparklineProps) {
  const { pts } = useMemo(
    () => computePoints(history, width, height),
    [history, width, height],
  );
  const midY = PAD_Y + (height - PAD_Y * 2) / 2;
  const path = useMemo(() => polylinePath(pts), [pts]);
  const areaAbove = useMemo(() => areaPath(pts, midY, 'above'), [pts, midY]);
  const areaBelow = useMemo(() => areaPath(pts, midY, 'below'), [pts, midY]);

  if (pts.length === 0) return null;

  return (
    <svg
      className="momentum-sparkline"
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={ariaLabel ?? `Score differential over the last ${pts.length} points`}
    >
      <line
        x1={PAD_X}
        x2={width - PAD_X}
        y1={midY}
        y2={midY}
        stroke="currentColor"
        strokeWidth={1}
        opacity={0.2}
      />
      <path d={areaAbove} fill={colorTeam1} opacity={0.35} />
      <path d={areaBelow} fill={colorTeam2} opacity={0.35} />
      <path
        d={path}
        fill="none"
        stroke="currentColor"
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity={0.85}
      />
    </svg>
  );
}
