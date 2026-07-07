import { ReactNode } from 'react';
import { useI18n } from '../../i18n';

/** Sticky bar that floats at the bottom of the viewport while a team list has a
 *  selection, putting the bulk action (add / remove / delete) within thumb
 *  reach in portrait. Renders nothing when the selection is empty. Pages keep at
 *  most one selection active at a time so two bars never overlap. */
export default function BulkActionBar({
  count,
  onClear,
  children,
}: {
  count: number;
  onClear: () => void;
  children: ReactNode;
}) {
  const { t } = useI18n();
  if (count === 0) return null;
  return (
    <div className="acc-bulkbar" role="region" aria-label={t('acc.teams.bulkBarLabel')}>
      <span className="acc-bulkbar__count">{t('acc.teams.selectedCount', { n: count })}</span>
      <div className="acc-bulkbar__actions">
        {children}
        <button className="acc-btn ghost" onClick={onClear}>
          {t('acc.teams.clearSelection')}
        </button>
      </div>
    </div>
  );
}
