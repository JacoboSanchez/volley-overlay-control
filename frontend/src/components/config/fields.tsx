import type { ReactNode } from 'react';
import ColorPicker from '../ColorPicker';

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
  label: ReactNode;
  color: string;
  onChange: (color: string) => void;
  testId?: string;
}

export function ConfigColorField({ label, color, onChange, testId }: ConfigColorFieldProps) {
  return (
    <div className="config-color-group">
      <label className="config-label">{label}</label>
      <ColorPicker color={color} onChange={onChange} data-testid={testId} />
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
  return (
    <div className="config-range-row">
      <label className="config-label">{label}</label>
      <input
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
