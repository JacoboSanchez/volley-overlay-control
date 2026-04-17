import React, { useState, useRef, useEffect, useCallback } from 'react';
import { HexColorPicker } from 'react-colorful';
import { useI18n } from '../i18n';

const PRESET_COLORS = [
  '#ffffff', '#000000', '#060f8a', '#d32f2f', '#f9a825',
  '#2e7d32', '#1565c0', '#6a1b9a', '#e65100', '#00838f',
  '#4e342e', '#546e7a',
];

const LS_KEY = 'volley_recentColors';
const MAX_RECENT = 8;

function getRecentColors() {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (raw) return JSON.parse(raw);
  } catch (e) { /* ignore */ }
  return [];
}

function saveRecentColor(color) {
  const normalized = color.toLowerCase();
  try {
    const recent = getRecentColors().filter((c) => c !== normalized);
    recent.unshift(normalized);
    localStorage.setItem(LS_KEY, JSON.stringify(recent.slice(0, MAX_RECENT)));
  } catch (e) { /* ignore */ }
}

/**
 * Color picker with a swatch trigger that opens a popover with preset colors,
 * recently used colors, a full spectrum picker, and hex input.
 * Drop-in replacement for <input type="color">.
 */
export default function ColorPicker({ color, onChange, className, 'data-testid': testId }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [hex, setHex] = useState(color ?? '#000000');
  const [recentColors, setRecentColors] = useState([]);
  const [popoverStyle, setPopoverStyle] = useState({});
  const popover = useRef(null);
  const swatch = useRef(null);

  // Load recent colors when popover opens
  useEffect(() => {
    if (open) setRecentColors(getRecentColors());
  }, [open]);

  // Compute fixed position relative to viewport when opening;
  // recompute on resize/orientation change so it stays visible.
  useEffect(() => {
    if (!open) {
      setPopoverStyle({});
      return;
    }

    const updatePosition = () => {
      if (!swatch.current) return;
      const rect = swatch.current.getBoundingClientRect();
      const popoverWidth = 232; // 200px picker + 2×8px padding + 2×1px border + buffer
      const popoverHeight = 340; // approx height of full popover
      const gap = 4;

      const style = {};
      const margin = 4;
      const maxTop = window.innerHeight - margin;

      // Vertical: prefer below swatch, flip above if not enough space below
      let top;
      if (rect.bottom + gap + popoverHeight > window.innerHeight && rect.top - gap - popoverHeight > 0) {
        top = rect.top - gap - popoverHeight;
      } else {
        top = rect.bottom + gap;
      }
      // Clamp so the popover stays within the viewport
      style.top = Math.max(margin, Math.min(top, maxTop - popoverHeight));

      // Limit height to available space and allow scrolling if needed
      style.maxHeight = window.innerHeight - style.top - margin;
      style.overflowY = 'auto';

      // Horizontal: prefer left-aligned with swatch, shift left if it would overflow
      if (rect.left + popoverWidth > window.innerWidth) {
        style.left = Math.max(4, window.innerWidth - popoverWidth - 4);
      } else {
        style.left = Math.max(4, rect.left);
      }

      setPopoverStyle(style);
    };

    updatePosition();
    window.addEventListener('resize', updatePosition);
    return () => window.removeEventListener('resize', updatePosition);
  }, [open]);

  // Sync local hex when prop changes externally
  useEffect(() => {
    setHex(color ?? '#000000');
  }, [color]);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    function handleClick(e) {
      if (
        popover.current && !popover.current.contains(e.target) &&
        swatch.current && !swatch.current.contains(e.target)
      ) {
        setOpen(false);
      }
    }
    document.addEventListener('pointerdown', handleClick);
    return () => document.removeEventListener('pointerdown', handleClick);
  }, [open]);

  const applyColor = useCallback((newColor) => {
    setHex(newColor);
    onChange(newColor);
    saveRecentColor(newColor);
    setRecentColors(getRecentColors());
  }, [onChange]);

  const handlePickerChange = useCallback((newColor) => {
    setHex(newColor);
    onChange(newColor);
  }, [onChange]);

  const handlePickerChangeEnd = useCallback((newColor) => {
    saveRecentColor(newColor);
    setRecentColors(getRecentColors());
  }, []);

  const handleHexInput = useCallback((e) => {
    const val = e.target.value;
    setHex(val);
    if (/^#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})$/.test(val)) {
      onChange(val);
    }
  }, [onChange]);

  const handleHexBlur = useCallback(() => {
    if (/^#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})$/.test(hex)) {
      saveRecentColor(hex);
      setRecentColors(getRecentColors());
    }
  }, [hex]);

  return (
    <div className="color-picker-wrapper">
      <button
        ref={swatch}
        type="button"
        className={`color-picker-swatch ${className ?? ''}`}
        style={{ backgroundColor: color ?? '#000000' }}
        onClick={() => setOpen(!open)}
        data-testid={testId}
        aria-label="Pick color"
      />
      {open && (
        <div ref={popover} className="color-picker-popover" style={popoverStyle}>
          <div className="color-picker-presets" data-testid={testId ? `${testId}-presets` : undefined}>
            <span className="color-picker-section-label">{t('colorPicker.presets')}</span>
            <div className="color-picker-swatch-row">
              {PRESET_COLORS.map((c) => (
                <button
                  key={c}
                  type="button"
                  className={`color-picker-preset${hex.toLowerCase() === c ? ' active' : ''}`}
                  style={{ backgroundColor: c }}
                  onClick={() => applyColor(c)}
                  aria-label={c}
                />
              ))}
            </div>
          </div>
          {recentColors.length > 0 && (
            <div className="color-picker-recent" data-testid={testId ? `${testId}-recent` : undefined}>
              <span className="color-picker-section-label">{t('colorPicker.recent')}</span>
              <div className="color-picker-swatch-row">
                {recentColors.map((c) => (
                  <button
                    key={c}
                    type="button"
                    className={`color-picker-preset${hex.toLowerCase() === c ? ' active' : ''}`}
                    style={{ backgroundColor: c }}
                    onClick={() => applyColor(c)}
                    aria-label={c}
                  />
                ))}
              </div>
            </div>
          )}
          <div onPointerUp={() => handlePickerChangeEnd(hex)}>
            <HexColorPicker color={hex} onChange={handlePickerChange} />
          </div>
          <input
            type="text"
            className="color-picker-hex-input"
            value={hex}
            onChange={handleHexInput}
            spellCheck={false}
            maxLength={7}
            onBlur={handleHexBlur}
            data-testid={testId ? `${testId}-hex` : undefined}
          />
        </div>
      )}
    </div>
  );
}
