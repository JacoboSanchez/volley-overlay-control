import { memo } from 'react';
import { SET_SUMMARY_STYLES, type SetSummaryStyle } from '../api/board';
import VisualStylePicker from './VisualStylePicker';

export interface SetSummaryStylePickerProps {
  /** Current selection (mirrors ``state.set_summary_style`` from the backend). */
  value: SetSummaryStyle;
  /** Fired whenever the operator picks a different style. */
  onChange: (style: SetSummaryStyle) => void;
  /** When ``true``, the picker is read-only (used inside disabled flows). */
  disabled?: boolean | undefined;
  overlayStyle?: string | undefined;
  overlayTheme?: string | undefined;
}

/**
 * Picker for the set-summary overlay style. Mirrors the existing
 * visual gallery: browsing is local; confirming broadcasts the
 * selected variant to OBS without reloading.
 */
function SetSummaryStylePicker({
  value,
  onChange,
  disabled,
  overlayStyle,
  overlayTheme,
}: SetSummaryStylePickerProps) {
  return (
    <VisualStylePicker
      kind="summary"
      value={value}
      styles={SET_SUMMARY_STYLES}
      onChange={(style) => onChange(style as SetSummaryStyle)}
      disabled={disabled}
      overlayStyle={overlayStyle}
      overlayTheme={overlayTheme}
      testId="set-summary-style-picker"
    />
  );
}

export default memo(SetSummaryStylePicker);
