import { useEffect, useState } from 'react';

// Single module-scoped MutationObserver shared across every hook
// instance. The previous implementation created one observer per
// call site (TeamPanel × 2 + PointsHistoryStrip), all watching the
// same ``document.documentElement`` attribute changes — redundant,
// and a small but real wake-up for each theme toggle. We now keep
// one observer and fan out to subscribers.
type Subscriber = () => void;
const subscribers = new Set<Subscriber>();
let rootObserver: MutationObserver | null = null;

function ensureRootObserver(): void {
  if (rootObserver) return;
  if (typeof MutationObserver === 'undefined' || typeof document === 'undefined') {
    return;
  }
  rootObserver = new MutationObserver(() => {
    subscribers.forEach((cb) => cb());
  });
  rootObserver.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ['class', 'style'],
  });
}

function subscribe(cb: Subscriber): () => void {
  ensureRootObserver();
  subscribers.add(cb);
  return () => {
    subscribers.delete(cb);
    // Tear the observer down once nothing else is listening so we
    // don't keep a stray watcher alive for the rest of the page's
    // lifetime when all theme-aware consumers have unmounted.
    if (subscribers.size === 0 && rootObserver) {
      rootObserver.disconnect();
      rootObserver = null;
    }
  };
}

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
    const raw = getComputedStyle(document.documentElement).getPropertyValue(varName).trim();
    return raw || fallback;
  };

  const [value, setValue] = useState<string>(read);

  useEffect(() => {
    const update = () => setValue(read());
    update();
    return subscribe(update);
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
