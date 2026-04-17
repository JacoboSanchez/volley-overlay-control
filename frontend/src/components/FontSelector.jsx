import React, { useState, useEffect, useRef } from 'react';
import { FONT_OPTIONS } from '../theme';

function fontPreviewStyle(name) {
  return name !== 'Default' ? { fontFamily: `'${name}'` } : undefined;
}

/**
 * Custom font selector — shows font name in default font + "25-25" preview in that font.
 */
export default function FontSelector({ value, onChange }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return;
    function handleClick(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener('pointerdown', handleClick);
    return () => document.removeEventListener('pointerdown', handleClick);
  }, [open]);

  return (
    <div className="font-selector" ref={ref} data-testid="font-selector">
      <button className="font-selector-trigger" onClick={() => setOpen(!open)} type="button">
        <span className="font-selector-name">{value}</span>
        <span className="font-selector-preview" style={fontPreviewStyle(value)}>
          25-25
        </span>
        <span className="material-icons font-selector-chevron">
          {open ? 'expand_less' : 'expand_more'}
        </span>
      </button>
      {open && (
        <div className="font-selector-dropdown">
          {FONT_OPTIONS.map((name) => (
            <button key={name} type="button"
              className={`font-selector-option ${name === value ? 'font-selector-option-active' : ''}`}
              onClick={() => { onChange(name); setOpen(false); }}>
              <span className="font-selector-name">{name}</span>
              <span className="font-selector-preview" style={fontPreviewStyle(name)}>
                25-25
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
