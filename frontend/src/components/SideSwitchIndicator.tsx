import { useI18n } from '../i18n';
import type { GameState } from '../api/client';

export interface SideSwitchIndicatorProps {
  /**
   * The ``beach_side_switch`` field of the current ``GameState``.
   * ``null``/``undefined`` (e.g. indoor matches) renders nothing.
   */
  info: GameState['beach_side_switch'] | null | undefined;
}

export default function SideSwitchIndicator({ info }: SideSwitchIndicatorProps) {
  const { t } = useI18n();
  if (!info) return null;

  const pending = info.is_switch_pending;
  const label = pending
    ? t('rules.sideSwitchPending')
    : t('rules.sideSwitchInN').replace('{{n}}', String(info.points_until_switch));

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
