import type { TeamState } from '../api/client';

/** Sum a team's per-set scores into a single number (0 for a missing team or
 *  empty scores). Used as a cheap "did scoring change" signal for cache keys. */
export function teamScoreSum(team: TeamState | undefined | null): number {
  if (!team) return 0;
  let total = 0;
  for (const value of Object.values(team.scores ?? {})) {
    if (typeof value === 'number') total += value;
  }
  return total;
}
