import { useI18n } from '../i18n';
import type { GameState } from '../api/client';

export interface ServeSwitchIndicatorProps {
  /**
   * The ``serve_switch`` field of the current ``GameState``.
   * ``null``/``undefined`` (every non-table-tennis mode, where serve
   * follows the rally winner) renders nothing.
   */
  info: GameState['serve_switch'] | null | undefined;
}

/**
 * Table-tennis serve-rotation chip. Mirrors ``SideSwitchIndicator``:
 * a countdown to the next serve handover, collapsing to a pulsing
 * "serve changes now" pill the moment a point hands the serve over.
 */
export default function ServeSwitchIndicator({ info }: ServeSwitchIndicatorProps) {
  const { t } = useI18n();
  if (!info) return null;

  const pending = info.is_change_pending;
  const label = pending
    ? t('rules.serveSwitchPending')
    : t('rules.serveSwitchInN', { n: info.points_until_change });

  return (
    <div
      className={`serve-switch-indicator ${pending ? 'serve-switch-indicator-pending' : ''}`}
      data-testid="serve-switch-indicator"
      role="status"
      aria-live={pending ? 'polite' : 'off'}
    >
      <span className="material-icons">{pending ? 'change_circle' : 'sports_tennis'}</span>
      <span>{label}</span>
    </div>
  );
}
