import { useI18n } from '../i18n';
import type { GameState } from '../api/client';

export interface SideSwitchIndicatorProps {
  /**
   * The ``beach_side_switch`` field of the current ``GameState``.
   * ``null``/``undefined`` (e.g. indoor matches) renders only the
   * transient ``forcePending`` pill, if any.
   */
  info: GameState['beach_side_switch'] | null | undefined;
  /**
   * Force-render the pulsing "Switch sides now" pill regardless of
   * ``info``. Used by the indoor-mode transient alert at the
   * deciding-set midpoint — there's no countdown to show, just the
   * immediate trigger, so the indicator collapses to the pending
   * variant without the "in N points" branch.
   */
  forcePending?: boolean;
}

export default function SideSwitchIndicator({
  info,
  forcePending = false,
}: SideSwitchIndicatorProps) {
  const { t } = useI18n();
  if (!info && !forcePending) return null;

  const pending = forcePending || (info?.is_switch_pending ?? false);
  // The countdown branch only makes sense when the backend supplied
  // ``info`` (beach mode); the indoor transient alert has no notion
  // of "points until next switch", so it always renders pending.
  const label = pending || !info
    ? t('rules.sideSwitchPending')
    : t('rules.sideSwitchInN', { n: info.points_until_switch });

  return (
    <div
      className={`side-switch-indicator ${pending ? 'side-switch-indicator-pending' : ''}`}
      data-testid="side-switch-indicator"
      role="status"
      aria-live={pending ? 'polite' : 'off'}
    >
      <span className="material-icons">{pending ? 'swap_horiz' : 'sync'}</span>
      <span>{label}</span>
    </div>
  );
}
