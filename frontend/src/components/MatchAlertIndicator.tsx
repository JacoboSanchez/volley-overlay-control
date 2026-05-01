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
  /**
   * Layout orientation, used to pick the direction of the team-pointing
   * triangle: left/right in landscape (where team panels sit on either
   * side of the centre column), up/down in portrait (where they stack).
   * Defaults to landscape — the icon still encodes the team correctly.
   */
  isPortrait?: boolean;
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

export default function MatchAlertIndicator({
  state,
  isPortrait = false,
}: MatchAlertIndicatorProps) {
  const { t } = useI18n();
  if (!state) return null;
  const alert = pickAlert(state);
  if (!alert) return null;

  const labelKey =
    alert.kind === 'finished' ? 'alerts.matchFinished'
    : alert.kind === 'match-point' ? 'alerts.matchPoint'
    : 'alerts.setPoint';
  const label = t(labelKey);

  // For team-bearing alerts (set / match point) the icon is a filled
  // triangle pointing toward the team that can win — mirroring the
  // panel's physical position: left/up for team 1, right/down for
  // team 2. Match-finished has no team, so it keeps the trophy.
  const icon =
    alert.kind === 'finished' ? 'emoji_events'
    : alert.team === 1 ? (isPortrait ? 'arrow_drop_up' : 'arrow_left')
    : alert.team === 2 ? (isPortrait ? 'arrow_drop_down' : 'arrow_right')
    : 'emoji_events';

  // The icon also sits on the side closest to the team — left for
  // team 1, right for team 2 — so the triangle's tip and its
  // position both reinforce the team identity. Match-finished pins
  // to the left like every other "lead" pill.
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
