import React from 'react';

/**
 * Score history table showing per-set scores.
 * Mirrors the NiceGUI center panel score columns.
 */
export default function ScoreTable({ state, setsLimit, currentSet }) {
  if (!state) return null;

  const matchFinished = state.match_finished;
  const rows = [];

  // Find the last set with non-zero scores
  let lastNonEmpty = 1;
  for (let i = 1; i <= setsLimit; i++) {
    const a = state.team_1.scores[`set_${i}`] ?? 0;
    const b = state.team_2.scores[`set_${i}`] ?? 0;
    if (a + b > 0) lastNonEmpty = i;
  }

  for (let i = 1; i <= setsLimit; i++) {
    const a = state.team_1.scores[`set_${i}`] ?? 0;
    const b = state.team_2.scores[`set_${i}`] ?? 0;

    // Break conditions matching NiceGUI logic
    if (i > 1 && i > lastNonEmpty) break;
    if (i === currentSet && i < setsLimit && !matchFinished) break;

    rows.push(
      <tr key={i} className={i === currentSet ? 'current-set-row' : ''}>
        <td
          className={a > b ? 'score-bold' : ''}
          data-testid={`team-1-set-${i}-score`}
        >
          {String(a).padStart(2, '0')}
        </td>
        <td className="set-number-cell">S{i}</td>
        <td
          className={b > a ? 'score-bold' : ''}
          data-testid={`team-2-set-${i}-score`}
        >
          {String(b).padStart(2, '0')}
        </td>
      </tr>
    );
  }

  if (rows.length === 0) return null;

  return (
    <table className="score-table">
      <tbody>{rows}</tbody>
    </table>
  );
}
