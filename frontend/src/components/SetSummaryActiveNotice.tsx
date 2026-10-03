import { memo } from 'react';
import { useI18n } from '../i18n';

export interface SetSummaryActiveNoticeProps {
  /** Resolved set the overlay is currently showing (server-side). */
  setNum: number | null | undefined;
  /** Show the "on air" line. Only needed when the full-frame preview can't
   *  render (links not loaded yet or unavailable) — otherwise the preview of
   *  the recap above the button already says it all. */
  showStatus?: boolean | undefined;
  /** Render just the button, sized to sit in the centre column's alerts row. */
  inline?: boolean | undefined;
  /** Disables the hide button (e.g. while the request is in flight). */
  busy?: boolean;
  onDeactivate: () => void;
}

/**
 * Centre-panel controls shown while the set-summary overlay is live.
 * CenterPanel renders the full-frame overlay preview alongside it, so
 * the operator sees exactly what is on air and can take it down.
 * Style changes live in the config panel's recap section.
 */
function SetSummaryActiveNotice({
  setNum,
  showStatus = false,
  inline = false,
  busy,
  onDeactivate,
}: SetSummaryActiveNoticeProps) {
  const { t } = useI18n();
  const displaySet = setNum && setNum > 0 ? setNum : '–';
  return (
    <div
      className={`set-summary-notice${inline ? ' set-summary-notice-inline' : ''}`}
      data-testid="set-summary-notice"
    >
      {showStatus && (
        <p className="set-summary-notice-body" data-testid="set-summary-notice-status">
          <span className="set-summary-notice-dot" aria-hidden="true" />
          {t('setSummary.activeBody', { n: displaySet })}
        </p>
      )}
      <button
        type="button"
        className="set-summary-notice-cta"
        onClick={onDeactivate}
        disabled={busy}
        data-testid="set-summary-notice-deactivate"
      >
        {t('setSummary.hide')}
      </button>
    </div>
  );
}

export default memo(SetSummaryActiveNotice);
