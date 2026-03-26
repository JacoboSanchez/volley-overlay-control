import React, { useState, useEffect, useRef } from 'react';

/**
 * Dialog for setting a custom score or set value.
 * Mirrors the NiceGUI custom_value_dialog.
 */
export default function SetValueDialog({ open, title, initialValue, maxValue, onSubmit, onClose }) {
  const [value, setValue] = useState(initialValue ?? 0);
  const inputRef = useRef(null);

  useEffect(() => {
    if (open) {
      setValue(initialValue ?? 0);
      setTimeout(() => inputRef.current?.select(), 50);
    }
  }, [open, initialValue]);

  if (!open) return null;

  const handleSubmit = (e) => {
    e.preventDefault();
    const clamped = Math.max(0, Math.min(maxValue, Math.round(value)));
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
            onChange={(e) => setValue(Number(e.target.value))}
          />
          <div className="dialog-actions">
            <button type="submit" className="dialog-btn dialog-btn-ok">
              <span className="material-icons">done</span>
              OK
            </button>
            <button type="button" className="dialog-btn dialog-btn-cancel" onClick={onClose}>
              <span className="material-icons">close</span>
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
