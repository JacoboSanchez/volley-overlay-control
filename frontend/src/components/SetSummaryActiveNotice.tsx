import { memo } from 'react';
import { useI18n } from '../i18n';
import SetSummaryStylePicker from './SetSummaryStylePicker';
import type { SetSummaryStyle } from '../api/client';

export interface SetSummaryActiveNoticeProps {
  /** Resolved set the overlay is currently showing (server-side). */
  setNum: number | null | undefined;
  /** Current style; populates the inline picker. */
  style: SetSummaryStyle;
  /** Disables the toggle off / style picker (e.g. while the request is in flight). */
  busy?: boolean;
  onDeactivate: () => void;
  onChangeStyle: (style: SetSummaryStyle) => void;
}

/**
 * Centre-panel notice shown while the set-summary overlay is live.
 * Replaces the preview/history widget so the operator never forgets
 * the recap is on air, and surfaces the style picker for live tweaks.
 */
function SetSummaryActiveNotice({
  setNum,
  style,
  busy,
  onDeactivate,
  onChangeStyle,
}: SetSummaryActiveNoticeProps) {
  const { t } = useI18n();
  const displaySet = setNum && setNum > 0 ? setNum : '–';
  return (
    <div className="set-summary-notice" data-testid="set-summary-notice">
      <p className="set-summary-notice-body">
        <span className="set-summary-notice-dot" aria-hidden="true" />
        {t('setSummary.activeBody', { n: displaySet })}
      </p>
      <SetSummaryStylePicker
        value={style}
        onChange={onChangeStyle}
        disabled={busy}
      />
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
