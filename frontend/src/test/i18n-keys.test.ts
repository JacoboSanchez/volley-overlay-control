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
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { translations } from '../i18n/translations';

const SRC_DIR = join(dirname(fileURLToPath(import.meta.url)), '..');

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) {
      return name === 'test' ? [] : sourceFiles(full);
    }
    return /\.(ts|tsx)$/.test(name) && !name.endsWith('.d.ts') ? [full] : [];
  });
}

describe('translation catalog', () => {
  const langs = Object.keys(translations);
  const enKeys = new Set(Object.keys(translations.en));

  it.each(langs.filter((l) => l !== 'en'))('%s has key parity with en', (lang) => {
    const keys = new Set(Object.keys(translations[lang]));
    const missing = [...enKeys].filter((k) => !keys.has(k));
    const extra = [...keys].filter((k) => !enKeys.has(k));
    expect({ missing, extra }).toEqual({ missing: [], extra: [] });
  });

  it('every static t(...) key used in src/ exists in the en catalog', () => {
    const used = new Set<string>();
    for (const file of sourceFiles(SRC_DIR)) {
      const text = readFileSync(file, 'utf-8');
      for (const m of text.matchAll(/\bt\(\s*'([^']+)'/g)) {
        used.add(m[1]);
      }
    }
    expect(used.size).toBeGreaterThan(100); // sanity: the scan found real usage
    const unresolved = [...used].filter((k) => !enKeys.has(k)).sort();
    expect(unresolved).toEqual([]);
  });
});
