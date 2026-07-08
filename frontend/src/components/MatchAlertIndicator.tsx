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
  /**
   * Display-side swap: when ``true`` team 1 sits on the right and team 2
   * on the left. The marker points at the team's *physical* side, so it
   * has to flip with the swap — otherwise a set/match-point arrow points
   * away from the team that can actually win it.
   */
  sidesSwapped?: boolean;
}

export type AlertKind = 'finished' | 'match-point' | 'set-point';

export interface AlertSpec {
  kind: AlertKind;
  team?: 1 | 2;
}

// Triangle that points toward a *physical* side of the layout: up/left
// for the left side, down/right for the right — picking the orientation
// that matches the current viewport. Keyed by side (not team) so it
// follows a side swap.
const SIDE_TRIANGLE = {
  left: { portrait: 'arrow_drop_up', landscape: 'arrow_left' },
  right: { portrait: 'arrow_drop_down', landscape: 'arrow_right' },
} as const;

/**
 * Resolve the highest-priority alert encoded in *state*. Exported so
 * effect hooks (haptics, future sound cues) can subscribe to the
 * same transitions the indicator pill renders.
 */
export function pickAlert(state: GameState | null | undefined): AlertSpec | null {
  if (!state) return null;
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
  sidesSwapped = false,
}: MatchAlertIndicatorProps) {
  const { t } = useI18n();
  if (!state) return null;
  const alert = pickAlert(state);
  if (!alert) return null;

  const labelKey =
    alert.kind === 'finished'
      ? 'alerts.matchFinished'
      : alert.kind === 'match-point'
        ? 'alerts.matchPoint'
        : 'alerts.setPoint';
  const label = t(labelKey);

  // Which physical side the alert's team currently sits on. Team 1 is on
  // the left by default; a side swap puts it on the right. Match-finished
  // has no team, so it pins to the left like every other "lead" pill.
  const onLeft = alert.team ? (alert.team === 1) !== sidesSwapped : true;

  // For team-bearing alerts (set / match point) the icon is a filled
  // triangle pointing toward the side the team can win on. Match-finished
  // keeps the trophy.
  const icon = alert.team
    ? SIDE_TRIANGLE[onLeft ? 'left' : 'right'][isPortrait ? 'portrait' : 'landscape']
    : 'emoji_events';

  // The icon sits on the same physical side it points to, so the
  // triangle's tip and its position both reinforce where the team is.
  const iconLeft = onLeft;
  const iconEl = <span className="material-icons">{icon}</span>;

  // Screen readers can't see the icon's position, so spell the team out
  // in the accessible name.
  const ariaLabel = alert.team ? `${label} — ${t('alerts.team', { team: alert.team })}` : label;

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
