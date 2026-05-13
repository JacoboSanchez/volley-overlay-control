import { useEffect, useState } from 'react';

/**
 * Read a CSS custom property from ``:root`` and re-read it whenever the
 * documentElement's class list changes (i.e. on theme toggles). The
 * value is normalised to a 6-digit hex string when possible, so the
 * contrast helpers can consume it directly.
 *
 * Falls back to ``fallback`` during SSR or when the variable is unset.
 */
export function useCssVariableColor(varName: string, fallback: string): string {
  const read = (): string => {
    if (typeof window === 'undefined' || typeof document === 'undefined') {
      return fallback;
    }
    const raw = getComputedStyle(document.documentElement)
      .getPropertyValue(varName)
      .trim();
    return raw || fallback;
  };

  const [value, setValue] = useState<string>(read);

  useEffect(() => {
    if (typeof MutationObserver === 'undefined') return;
    const update = () => setValue(read());
    update();
    const observer = new MutationObserver(update);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['class', 'style'],
    });
    return () => observer.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [varName, fallback]);

  return value;
}

/**
 * Current value of ``--surface`` — the background colour underneath the
 * team panel. Used to derive readable variants of team colors.
 */
export function useSurfaceColor(): string {
  return useCssVariableColor('--surface', '#16213e');
}
