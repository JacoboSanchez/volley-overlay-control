import { useId, type ReactNode } from 'react';
import ColorPicker from '../ColorPicker';
import { useI18n } from '../../i18n';

export interface ConfigSwitchProps {
  label: ReactNode;
  checked: boolean;
  onChange: (checked: boolean) => void;
  testId?: string;
}

export function ConfigSwitch({ label, checked, onChange, testId }: ConfigSwitchProps) {
  return (
    <div className="config-switch-row">
      <label className="config-switch-label">
        <input
          type="checkbox"
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
          data-testid={testId}
        />
        {label}
      </label>
    </div>
  );
}

export interface ConfigColorFieldProps {
  /** Plain-text label — also announced by the swatch button, so every
   *  picker on the screen is distinguishable to assistive tech. */
  label: string;
  color: string;
  onChange: (color: string) => void;
  testId?: string;
}

export function ConfigColorField({ label, color, onChange, testId }: ConfigColorFieldProps) {
  return (
    <div className="config-color-group">
      <label className="config-label">{label}</label>
      <ColorPicker color={color} onChange={onChange} data-testid={testId} aria-label={label} />
    </div>
  );
}

export interface ConfigRangeProps {
  label: ReactNode;
  value: number;
  min: number;
  max: number;
  step?: number;
  onChange: (value: number) => void;
}

export function ConfigRange({ label, value, min, max, step = 1, onChange }: ConfigRangeProps) {
  const id = useId();
  return (
    <div className="config-range-row">
      <label className="config-label" htmlFor={id}>
        {label}
      </label>
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="config-range"
      />
    </div>
  );
}

/** One-line notice for sections whose controls persist as soon as they are
 *  touched (localStorage settings or instant server calls) — distinguishing
 *  them from the staged sections that wait for the Save button. */
export function InstantHint() {
  const { t } = useI18n();
  return (
    <p className="config-hint config-instant-hint">
      <span className="material-icons" aria-hidden="true">
        bolt
      </span>
      {t('config.appliesImmediately')}
    </p>
  );
}
