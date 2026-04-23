import { useState, useEffect, useRef, FormEvent } from 'react';
import { useI18n } from '../i18n';

export interface SetValueDialogProps {
  open: boolean;
  title: string;
  initialValue?: number;
  maxValue: number;
  onSubmit: (value: number) => void;
  onClose: () => void;
}

/**
 * Dialog for setting a custom score or set value.
 * Mirrors the NiceGUI custom_value_dialog.
 */
export default function SetValueDialog({
  open,
  title,
  initialValue,
  maxValue,
  onSubmit,
  onClose,
}: SetValueDialogProps) {
  const { t } = useI18n();
  const [value, setValue] = useState<number | ''>(initialValue ?? 0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setValue(initialValue ?? 0);
      setTimeout(() => inputRef.current?.select(), 50);
    }
  }, [open, initialValue]);

  if (!open) return null;

  const handleSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const num = Number(value);
    const safe = Number.isFinite(num) ? num : 0;
    const clamped = Math.max(0, Math.min(maxValue, Math.round(safe)));
    onSubmit(clamped);
  };

  return (
    <div className="dialog-overlay" onClick={onClose}>
      <div className="dialog-card" onClick={(e) => e.stopPropagation()}>
        <form onSubmit={handleSubmit}>
          <h3 className="dialog-title">{title}</h3>
          <input
            ref={inputRef}
            type="number"
            className="dialog-input"
            min={0}
            max={maxValue}
            step={1}
            value={value}
            onChange={(e) => setValue(e.target.value === '' ? '' : Number(e.target.value))}
          />
          <div className="dialog-actions">
            <button type="submit" className="dialog-btn dialog-btn-ok">
              <span className="material-icons">done</span>
              {t('dialog.ok')}
            </button>
            <button type="button" className="dialog-btn dialog-btn-cancel" onClick={onClose}>
              <span className="material-icons">close</span>
              {t('dialog.cancel')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
