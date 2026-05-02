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

  it('omits the team from the visible label (icon position is the cue)', () => {
    renderWithI18n(
      <MatchAlertIndicator state={withInfo({}, { team_1_set_point: true })} />,
    );
    const el = screen.getByTestId('match-alert-indicator');
    expect(el.textContent).not.toMatch(/team|equipo|equipa|squadra|équipe/i);
  });

  it('places the icon before the label for team 1', () => {
    renderWithI18n(
      <MatchAlertIndicator state={withInfo({}, { team_1_match_point: true })} />,
    );
    const el = screen.getByTestId('match-alert-indicator');
    const children = Array.from(el.children) as HTMLElement[];
    const iconIdx = children.findIndex((c) => c.classList.contains('material-icons'));
    const labelIdx = children.findIndex((c) => !c.classList.contains('material-icons'));
    expect(iconIdx).toBeGreaterThanOrEqual(0);
    expect(iconIdx).toBeLessThan(labelIdx);
  });

  it('places the icon after the label for team 2', () => {
    renderWithI18n(
      <MatchAlertIndicator state={withInfo({}, { team_2_match_point: true })} />,
    );
    const el = screen.getByTestId('match-alert-indicator');
    const children = Array.from(el.children) as HTMLElement[];
    const iconIdx = children.findIndex((c) => c.classList.contains('material-icons'));
    const labelIdx = children.findIndex((c) => !c.classList.contains('material-icons'));
    expect(iconIdx).toBeGreaterThanOrEqual(0);
    expect(iconIdx).toBeGreaterThan(labelIdx);
  });

  it('exposes the team in the aria-label for screen readers', () => {
    renderWithI18n(
      <MatchAlertIndicator state={withInfo({}, { team_2_set_point: true })} />,
    );
    const el = screen.getByTestId('match-alert-indicator');
    // The visible text drops the team, but assistive tech still gets it.
    expect(el.getAttribute('aria-label')).toMatch(/2/);
  });

  // ── Team-pointing triangle icon ────────────────────────────────────

  it('uses a left-pointing triangle for team 1 in landscape', () => {
    renderWithI18n(
      <MatchAlertIndicator
        state={withInfo({}, { team_1_set_point: true })}
        isPortrait={false}
      />,
    );
    const icon = screen.getByTestId('match-alert-indicator')
      .querySelector('.material-icons');
    expect(icon?.textContent).toBe('arrow_left');
  });

  it('uses a right-pointing triangle for team 2 in landscape', () => {
    renderWithI18n(
      <MatchAlertIndicator
        state={withInfo({}, { team_2_match_point: true })}
        isPortrait={false}
      />,
    );
    const icon = screen.getByTestId('match-alert-indicator')
      .querySelector('.material-icons');
    expect(icon?.textContent).toBe('arrow_right');
  });

  it('uses an up-pointing triangle for team 1 in portrait', () => {
    renderWithI18n(
      <MatchAlertIndicator
        state={withInfo({}, { team_1_set_point: true })}
        isPortrait={true}
      />,
    );
    const icon = screen.getByTestId('match-alert-indicator')
      .querySelector('.material-icons');
    expect(icon?.textContent).toBe('arrow_drop_up');
  });

  it('uses a down-pointing triangle for team 2 in portrait', () => {
    renderWithI18n(
      <MatchAlertIndicator
        state={withInfo({}, { team_2_match_point: true })}
        isPortrait={true}
      />,
    );
    const icon = screen.getByTestId('match-alert-indicator')
      .querySelector('.material-icons');
    expect(icon?.textContent).toBe('arrow_drop_down');
  });

  it('keeps the trophy icon for match-finished regardless of orientation', () => {
    for (const isPortrait of [true, false]) {
      const { unmount } = renderWithI18n(
        <MatchAlertIndicator
          state={withInfo({ match_finished: true })}
          isPortrait={isPortrait}
        />,
      );
      const icon = screen.getByTestId('match-alert-indicator')
        .querySelector('.material-icons');
      expect(icon?.textContent).toBe('emoji_events');
      unmount();
    }
  });
});
