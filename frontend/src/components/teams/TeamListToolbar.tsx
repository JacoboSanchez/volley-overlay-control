import { MutableRefObject, Ref, useEffect, useRef } from 'react';
import { useI18n } from '../../i18n';

/** Toolbar above a selectable team list: a select-all checkbox (with an
 *  indeterminate state when only some shown rows are selected) and an optional
 *  live filter with a "shown of total" counter so it's clear the list is
 *  filtered rather than just short. */
export default function TeamListToolbar({
  shownCount, selectedShownCount, onSelectAll, onClearSelection,
  query, onQuery, total, showFilter, inputRef,
}: {
  shownCount: number;
  selectedShownCount: number;
  onSelectAll: () => void;
  onClearSelection: () => void;
  query: string;
  onQuery: (value: string) => void;
  total: number;
  showFilter: boolean;
  /** Optional external ref to the select-all checkbox, so a page can restore
   *  focus here after a bulk action clears the selection (and unmounts the bar
   *  that held focus). */
  inputRef?: Ref<HTMLInputElement>;
}) {
  const { t } = useI18n();
  const ref = useRef<HTMLInputElement>(null);
  const all = shownCount > 0 && selectedShownCount === shownCount;
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = selectedShownCount > 0 && !all;
  }, [selectedShownCount, all]);

  // Assign both the internal ref (indeterminate state) and the caller's ref.
  const setRef = (el: HTMLInputElement | null) => {
    ref.current = el;
    if (typeof inputRef === 'function') inputRef(el);
    else if (inputRef) (inputRef as MutableRefObject<HTMLInputElement | null>).current = el;
  };

  return (
    <div className="acc-tlist-toolbar">
      <label className="acc-tlist-selall">
        <input
          ref={setRef}
          type="checkbox"
          checked={all}
          disabled={shownCount === 0}
          aria-label={all ? t('acc.common.deselectAll') : t('acc.common.selectAll')}
          onChange={() => (all ? onClearSelection() : onSelectAll())}
        />
        <span className="acc-muted">{t('acc.common.selectAll')}</span>
      </label>
      {showFilter && (
        <div className="acc-tfilter">
          <input
            className="acc-input"
            type="search"
            value={query}
            placeholder={t('acc.teams.searchPlaceholder')}
            aria-label={t('acc.teams.searchPlaceholder')}
            onChange={(e) => onQuery(e.target.value)}
          />
          <span className="acc-muted acc-tfilter__count">
            {t('acc.teams.showing', { shown: shownCount, total })}
          </span>
        </div>
      )}
    </div>
  );
}
