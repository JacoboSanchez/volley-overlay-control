import { ReactElement } from 'react';
import type { GameState } from '../api/client';

export interface ScoreTableProps {
  state: GameState | null | undefined;
  setsLimit: number;
  currentSet: number;
  teamId: 1 | 2;
}

function toNumber(v: unknown): number {
  return typeof v === 'number' ? v : typeof v === 'string' ? Number(v) || 0 : 0;
}

/**
 * Per-team score column showing scores for each completed set.
 */
export default function ScoreTable({ state, setsLimit, currentSet, teamId }: ScoreTableProps) {
  if (!state) return null;

  const matchFinished = state.match_finished;
  const teamState = teamId === 1 ? state.team_1 : state.team_2;
  const otherState = teamId === 1 ? state.team_2 : state.team_1;

  let lastNonEmpty = 1;
  for (let i = 1; i <= setsLimit; i++) {
    const a = toNumber(state.team_1.scores[`set_${i}`]);
    const b = toNumber(state.team_2.scores[`set_${i}`]);
    if (a + b > 0) lastNonEmpty = i;
  }

  const cells: ReactElement[] = [];
  for (let i = 1; i <= setsLimit; i++) {
    const score = toNumber(teamState.scores[`set_${i}`]);
    const otherScore = toNumber(otherState.scores[`set_${i}`]);

    if (i > 1 && i > lastNonEmpty) break;
    if (i === currentSet && i < setsLimit && !matchFinished) break;

    const isWinning = score > otherScore;

    cells.push(
      <div
        key={i}
        className={`score-cell ${i === currentSet ? 'score-cell-current' : ''} ${isWinning ? 'score-bold' : ''}`}
        data-testid={`team-${teamId}-set-${i}-score`}
      >
        {String(score).padStart(2, '0')}
      </div>
    );
  }

  if (cells.length === 0) return null;

  return (
    <div className="score-column">
      {cells}
    </div>
  );
}
