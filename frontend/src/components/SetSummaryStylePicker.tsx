import { memo } from 'react';
import { useI18n } from '../i18n';
import { SET_SUMMARY_STYLES, type SetSummaryStyle } from '../api/client';

export interface SetSummaryStylePickerProps {
  /** Current selection (mirrors ``state.set_summary_style`` from the backend). */
  value: SetSummaryStyle;
  /** Fired whenever the operator picks a different style. */
  onChange: (style: SetSummaryStyle) => void;
  /** When ``true``, the picker is read-only (used inside disabled flows). */
  disabled?: boolean;
}

/**
 * Picker for the set-summary overlay style. Mirrors the existing
 * preset-style flow: the operator chooses one of the seven candidate
 * variants and the backend broadcasts the change to OBS without
 * reloading.
 */
function SetSummaryStylePicker({ value, onChange, disabled }: SetSummaryStylePickerProps) {
  const { t } = useI18n();
  return (
    <div
      className="set-summary-style-picker"
      role="radiogroup"
      aria-label={t('config.setSummary.style.label')}
      data-testid="set-summary-style-picker"
    >
      {SET_SUMMARY_STYLES.map((style) => {
        const selected = style === value;
        return (
          <button
            key={style}
            type="button"
            role="radio"
            aria-checked={selected}
            aria-label={t(`setSummary.style.${style}`)}
            disabled={disabled}
            className={`set-summary-style-option${selected ? ' selected' : ''}`}
            data-testid={`set-summary-style-${style}`}
            onClick={() => {
              if (!disabled && !selected) onChange(style);
            }}
          >
            <span className="set-summary-style-name">{t(`setSummary.style.${style}`)}</span>
          </button>
        );
      })}
    </div>
  );
}

export default memo(SetSummaryStylePicker);
