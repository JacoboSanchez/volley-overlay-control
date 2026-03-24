import React from 'react';

/**
 * Per-team score column showing scores for each completed set.
 * Displayed directly below the team logo, no set number indicator.
 * Mirrors the NiceGUI center panel score columns layout.
 */
export default function ScoreTable({ state, setsLimit, currentSet, teamId }) {
  if (!state) return null;

  const matchFinished = state.match_finished;
  const teamState = teamId === 1 ? state.team_1 : state.team_2;
  const otherState = teamId === 1 ? state.team_2 : state.team_1;

  // Find the last set with non-zero scores
  let lastNonEmpty = 1;
  for (let i = 1; i <= setsLimit; i++) {
    const a = state.team_1.scores[`set_${i}`] ?? 0;
    const b = state.team_2.scores[`set_${i}`] ?? 0;
    if (a + b > 0) lastNonEmpty = i;
  }

  const cells = [];
  for (let i = 1; i <= setsLimit; i++) {
    const score = teamState.scores[`set_${i}`] ?? 0;
    const otherScore = otherState.scores[`set_${i}`] ?? 0;

    // Break conditions matching NiceGUI logic
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
