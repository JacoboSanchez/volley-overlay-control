import { useI18n } from '../i18n';
import type { GameState } from '../api/client';

export interface MatchAlertIndicatorProps {
  /**
   * Full game state. Drives ``match_finished`` (which preempts every
   * other alert) and the per-team set / match-point flags carried in
   * ``match_point_info``. ``null``/``undefined`` renders nothing —
   * matches the empty/loading state from the rest of the app.
   */
  state: GameState | null | undefined;
}

type AlertKind = 'finished' | 'match-point' | 'set-point';

interface AlertSpec {
  kind: AlertKind;
  team?: 1 | 2;
}

function pickAlert(state: GameState): AlertSpec | null {
  // Match end is the loudest event — render it on its own and skip
  // everything else so the operator's eye lands here first.
  if (state.match_finished) return { kind: 'finished' };

  const info = state.match_point_info;
  if (!info) return null;
  // Match point implies set point. Pick the more specific label so the
  // pill never reads "set point" when it really *is* a match point.
  if (info.team_1_match_point) return { kind: 'match-point', team: 1 };
  if (info.team_2_match_point) return { kind: 'match-point', team: 2 };
  if (info.team_1_set_point) return { kind: 'set-point', team: 1 };
  if (info.team_2_set_point) return { kind: 'set-point', team: 2 };
  return null;
}

export default function MatchAlertIndicator({ state }: MatchAlertIndicatorProps) {
  const { t } = useI18n();
  if (!state) return null;
  const alert = pickAlert(state);
  if (!alert) return null;

  const labelKey =
    alert.kind === 'finished' ? 'alerts.matchFinished'
    : alert.kind === 'match-point' ? 'alerts.matchPoint'
    : 'alerts.setPoint';
  const label = t(labelKey);

  const icon =
    alert.kind === 'finished' ? 'emoji_events'
    : alert.kind === 'match-point' ? 'sports_score'
    : 'flag';

  // The icon's position is the only cue for which team is on point —
  // left for team 1, right for team 2 — mirroring the team panels'
  // physical position on the layout. Match-finished has no team and
  // keeps the icon on the left like every other "lead" pill.
  const iconLeft = alert.team !== 2;
  const iconEl = <span className="material-icons">{icon}</span>;

  // Screen readers can't see the icon's position, so spell the team out
  // in the accessible name.
  const ariaLabel = alert.team
    ? `${label} — ${t('alerts.team', { team: alert.team })}`
    : label;

  return (
    <div
      className={`match-alert-indicator match-alert-indicator-${alert.kind}`}
      data-testid="match-alert-indicator"
      data-alert-kind={alert.kind}
      data-alert-team={alert.team ?? ''}
      role="status"
      aria-live="polite"
      aria-label={ariaLabel}
    >
      {iconLeft && iconEl}
      <span>{label}</span>
      {!iconLeft && iconEl}
    </div>
  );
}
