/// <reference types="vite/client" />
/**
 * Guards against translation-catalog drift:
 *
 * 1. Key parity — every language block must define exactly the same keys as
 *    the English base, so no locale silently falls back to English.
 * 2. Used keys resolve — every static `t('some.key')` literal in the source
 *    must exist in the English catalog, so a missing key can never leak the
 *    raw key string to the UI (dynamic template-literal keys are exercised
 *    by their components' own tests).
 */
import { describe, it, expect } from 'vitest';
import { translations } from '../i18n/translations';

// Raw source of everything under src/ except the tests themselves and
// generated type declarations.
const sources = import.meta.glob(
  ['../**/*.ts', '../**/*.tsx', '!../test/**', '!../**/*.d.ts'],
  { query: '?raw', import: 'default', eager: true },
) as Record<string, string>;

describe('translation catalog', () => {
  const langs = Object.keys(translations);
  const enKeys = new Set(Object.keys(translations.en ?? {}));

  it.each(langs.filter((l) => l !== 'en'))('%s has key parity with en', (lang) => {
    const keys = new Set(Object.keys(translations[lang] ?? {}));
    const missing = [...enKeys].filter((k) => !keys.has(k));
    const extra = [...keys].filter((k) => !enKeys.has(k));
    expect({ missing, extra }).toEqual({ missing: [], extra: [] });
  });

  it('every static t(...) key used in src/ exists in the en catalog', () => {
    const used = new Set<string>();
    expect(Object.keys(sources).length).toBeGreaterThan(50); // sanity: glob found the app
    for (const text of Object.values(sources)) {
      // Single/double-quoted keys, plus backtick keys with no ``${…}``
      // interpolation — dynamic template keys can't be checked statically
      // and are exercised by their components' own tests.
      for (const m of text.matchAll(/\bt\(\s*(?:'([^']+)'|"([^"]+)"|`([^`$]+)`)/g)) {
        const key = m[1] ?? m[2] ?? m[3];
        if (key) used.add(key);
      }
      // Ternary first-arguments — ``t(cond ? 'a' : 'b')`` — which the
      // literal-first regex above skips; both branches must resolve.
      for (const m of text.matchAll(
        /\bt\(\s*[^)'"`]*?\?\s*(?:'([^']+)'|"([^"]+)")\s*:\s*(?:'([^']+)'|"([^"]+)")/g,
      )) {
        for (const key of [m[1] ?? m[2], m[3] ?? m[4]]) {
          if (key) used.add(key);
        }
      }
    }
    expect(used.size).toBeGreaterThan(100); // sanity: the scan found real usage
    const unresolved = [...used].filter((k) => !enKeys.has(k)).sort();
    expect(unresolved).toEqual([]);
  });
});
