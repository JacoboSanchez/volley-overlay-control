import { describe, it, expect } from 'vitest';
import { USED_ICONS } from '../icons';

/**
 * The app ships a font subset containing only the icons in ``src/icons.ts``
 * (see ``scripts/icons/build_font_subset.py``). An icon used in the source
 * but missing from that list renders as its literal name — and only in
 * production, since neither the dev server nor these tests load the font.
 *
 * So the list has to be checked against the source mechanically. This test
 * is the reason the subset is safe to ship.
 */

// Raw source of everything under src/ except the tests themselves, which
// may name icons the app never draws. Same ``?raw`` glob the translation
// catalogue check uses, so no Node file APIs are needed here.
const sources = import.meta.glob(['../**/*.ts', '../**/*.tsx', '!../test/**', '!../**/*.d.ts'], {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;

/** Icon names written literally as a ``material-icons`` span's child. */
function literalIconsIn(source: string): string[] {
  const found: string[] = [];
  const span = /className=(?:"|\{`)material-icons[^"`]*(?:"|`\})([^]*?)<\/span>/g;
  for (const match of source.matchAll(span)) {
    const body = match[1]!.includes('>') ? match[1]!.split('>').slice(1).join('>') : match[1]!;
    const bare = body.trim();
    if (/^[a-z0-9_]+$/.test(bare)) found.push(bare);
    // A JSX expression child (a lookup, a ternary, a helper call) — any
    // quoted names inside it are icon names too.
    for (const quoted of body.matchAll(/'([a-z0-9_]+)'/g)) found.push(quoted[1]!);
  }
  return found;
}

describe('material-icons subset coverage', () => {
  const files = Object.values(sources);

  it('finds the icon usages it is supposed to be checking', () => {
    // Guard against the scan silently matching nothing (e.g. after a
    // refactor of how icons are rendered), which would make every
    // assertion below vacuously pass.
    const all = files.flatMap((f) => literalIconsIn(f));
    expect(all.length).toBeGreaterThan(50);
  });

  it('lists every icon rendered literally in the source', () => {
    const missing = new Set<string>();
    for (const file of files) {
      for (const icon of literalIconsIn(file)) {
        if (!USED_ICONS.includes(icon)) missing.add(icon);
      }
    }
    expect(
      [...missing].sort(),
      'Add these to src/icons.ts and rerun scripts/icons/build_font_subset.py',
    ).toEqual([]);
  });

  it('lists every icon named in a runtime lookup table', () => {
    // The tables that feed `<span className="material-icons">{expr}</span>`.
    // Matched by shape (a Record of string values whose name ends in ICON /
    // ICONS) so a new table is picked up without editing this test.
    const missing = new Set<string>();
    for (const file of files) {
      const source = file;
      const tables = source.matchAll(/const [A-Z_]*ICONS?\b[^=]*=\s*\{([^}]*)\}/g);
      for (const table of tables) {
        for (const value of table[1]!.matchAll(/:\s*'([a-z0-9_]+)'/g)) {
          if (!USED_ICONS.includes(value[1]!)) missing.add(value[1]!);
        }
      }
    }
    expect(
      [...missing].sort(),
      'Add these to DYNAMIC_ICONS in src/icons.ts and rebuild the subset',
    ).toEqual([]);
  });

  it('has no duplicate or malformed entries', () => {
    expect(new Set(USED_ICONS).size).toBe(USED_ICONS.length);
    for (const name of USED_ICONS) {
      expect(name, `${name} is not a valid ligature name`).toMatch(/^[a-z0-9_]+$/);
    }
  });
});
