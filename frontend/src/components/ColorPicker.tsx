import { useState, useRef, useEffect, useCallback, CSSProperties, ChangeEvent } from 'react';
import { HexColorPicker } from 'react-colorful';
import { useI18n } from '../i18n';

const PRESET_COLORS = [
  '#ffffff', '#000000', '#060f8a', '#d32f2f', '#f9a825',
  '#2e7d32', '#1565c0', '#6a1b9a', '#e65100', '#00838f',
  '#4e342e', '#546e7a',
];

const LS_KEY = 'volley_recentColors';
const MAX_RECENT = 8;

function getRecentColors(): string[] {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) return parsed.filter((c): c is string => typeof c === 'string');
    }
  } catch (e) { /* ignore */ }
  return [];
}

function saveRecentColor(color: string) {
  const normalized = color.toLowerCase();
  try {
    const recent = getRecentColors().filter((c) => c !== normalized);
    recent.unshift(normalized);
    localStorage.setItem(LS_KEY, JSON.stringify(recent.slice(0, MAX_RECENT)));
  } catch (e) { /* ignore */ }
}

export interface ColorPickerProps {
  color?: string;
  onChange: (color: string) => void;
  className?: string;
  'data-testid'?: string;
}

/**
 * Color picker with a swatch trigger that opens a popover with preset colors,
 * recently used colors, a full spectrum picker, and hex input.
 * Drop-in replacement for <input type="color">.
 */
export default function ColorPicker({
  color,
  onChange,
  className,
  'data-testid': testId,
}: ColorPickerProps) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [hex, setHex] = useState(color ?? '#000000');
  const [recentColors, setRecentColors] = useState<string[]>([]);
  const [popoverStyle, setPopoverStyle] = useState<CSSProperties>({});
  const popover = useRef<HTMLDivElement>(null);
  const swatch = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (open) setRecentColors(getRecentColors());
  }, [open]);

  useEffect(() => {
    if (!open) {
      setPopoverStyle({});
      return;
    }

    const updatePosition = () => {
      if (!swatch.current) return;
      const rect = swatch.current.getBoundingClientRect();
      const popoverWidth = 232;
      const popoverHeight = 340;
      const gap = 4;

      const style: CSSProperties = {};
      const margin = 4;
      const maxTop = window.innerHeight - margin;

      let top: number;
      if (rect.bottom + gap + popoverHeight > window.innerHeight && rect.top - gap - popoverHeight > 0) {
        top = rect.top - gap - popoverHeight;
      } else {
        top = rect.bottom + gap;
      }
      const clampedTop = Math.max(margin, Math.min(top, maxTop - popoverHeight));
      style.top = clampedTop;

      style.maxHeight = window.innerHeight - clampedTop - margin;
      style.overflowY = 'auto';

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

  useEffect(() => {
    setHex(color ?? '#000000');
  }, [color]);

  useEffect(() => {
    if (!open) return;
    function handleClick(e: PointerEvent) {
      const target = e.target as Node;
      if (
        popover.current && !popover.current.contains(target) &&
        swatch.current && !swatch.current.contains(target)
      ) {
        setOpen(false);
      }
    }
    document.addEventListener('pointerdown', handleClick);
    return () => document.removeEventListener('pointerdown', handleClick);
  }, [open]);

  const applyColor = useCallback((newColor: string) => {
    setHex(newColor);
    onChange(newColor);
    saveRecentColor(newColor);
    setRecentColors(getRecentColors());
  }, [onChange]);

  const handlePickerChange = useCallback((newColor: string) => {
    setHex(newColor);
    onChange(newColor);
  }, [onChange]);

  const handlePickerChangeEnd = useCallback((newColor: string) => {
    saveRecentColor(newColor);
    setRecentColors(getRecentColors());
  }, []);

  const handleHexInput = useCallback((e: ChangeEvent<HTMLInputElement>) => {
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
