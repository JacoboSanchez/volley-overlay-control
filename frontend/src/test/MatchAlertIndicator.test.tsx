import { describe, it, expect } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithI18n, mockGameState } from './helpers';
import MatchAlertIndicator from '../components/MatchAlertIndicator';
import type { GameState } from '../api/client';

const baseInfo = {
  team_1_set_point: false,
  team_2_set_point: false,
  team_1_match_point: false,
  team_2_match_point: false,
};

function withInfo(
  overrides: Partial<GameState>,
  info: Partial<typeof baseInfo> = {},
): GameState {
  return {
    ...mockGameState,
    match_point_info: { ...baseInfo, ...info },
    ...overrides,
  } as GameState;
}

describe('MatchAlertIndicator', () => {
  it('renders nothing when state is null', () => {
    renderWithI18n(<MatchAlertIndicator state={null} />);
    expect(screen.queryByTestId('match-alert-indicator')).toBeNull();
  });

  it('renders nothing when no flags are set', () => {
    renderWithI18n(<MatchAlertIndicator state={withInfo({})} />);
    expect(screen.queryByTestId('match-alert-indicator')).toBeNull();
  });

  it('renders the match-finished pill when match_finished is true', () => {
    renderWithI18n(
      <MatchAlertIndicator state={withInfo({ match_finished: true })} />,
    );
    const el = screen.getByTestId('match-alert-indicator');
    expect(el.dataset.alertKind).toBe('finished');
    // No team is associated with match-finished — leave the attribute empty.
    expect(el.dataset.alertTeam).toBe('');
  });

  it('match_finished overrides set/match-point flags', () => {
    renderWithI18n(
      <MatchAlertIndicator
        state={withInfo(
          { match_finished: true },
          { team_1_match_point: true, team_1_set_point: true },
        )}
      />,
    );
    expect(screen.getByTestId('match-alert-indicator').dataset.alertKind)
      .toBe('finished');
  });

  it('renders set-point team 1 when only team 1 has set point', () => {
    renderWithI18n(
      <MatchAlertIndicator
        state={withInfo({}, { team_1_set_point: true })}
      />,
    );
    const el = screen.getByTestId('match-alert-indicator');
    expect(el.dataset.alertKind).toBe('set-point');
    expect(el.dataset.alertTeam).toBe('1');
  });

  it('prefers match-point over set-point when both are true', () => {
    renderWithI18n(
      <MatchAlertIndicator
        state={withInfo(
          {},
          { team_2_set_point: true, team_2_match_point: true },
        )}
      />,
    );
    const el = screen.getByTestId('match-alert-indicator');
    expect(el.dataset.alertKind).toBe('match-point');
    expect(el.dataset.alertTeam).toBe('2');
  });

  it('renders set-point for team 2 when only team 2 has set point', () => {
    renderWithI18n(
      <MatchAlertIndicator
        state={withInfo({}, { team_2_set_point: true })}
      />,
    );
    const el = screen.getByTestId('match-alert-indicator');
    expect(el.dataset.alertKind).toBe('set-point');
    expect(el.dataset.alertTeam).toBe('2');
  });
});
