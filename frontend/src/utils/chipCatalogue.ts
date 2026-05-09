/**
 * Single source of truth for the action-chip palette.
 *
 * Mirrors the Python ``_CHIP_CATALOGUE`` in ``app/match_report.py``
 * so the live operator drawer, the post-match HTML report and any
 * future surface that reuses ``ActionChip`` paint the same colours
 * for the same action kinds. When updating the catalogue here,
 * keep the Python copy in sync — the legend renderer in the
 * report iterates this catalogue's order.
 */

export type ChipKind =
  | 'point-t1'
  | 'point-t2'
  | 'point'
  | 'set'
  | 'timeout'
  | 'serve'
  | 'edit'
  | 'reset'
  | 'undone'
  | 'other';

export interface ChipMeta {
  /** Single-character / emoji glyph rendered inside the accent strip. */
  glyph: string;
  /**
   * i18n key that names the chip in the timeline legend or in
   * screen-reader announcements. ``null`` for catalogue entries
   * that intentionally don't earn a legend row (the generic
   * ``point`` and the ``other`` fallback).
   */
  legendKey: string | null;
}

/**
 * Insertion order matters for legend / list rendering — match the
 * Python catalogue.
 */
export const CHIP_CATALOGUE: Record<ChipKind, ChipMeta> = {
  'point-t1': { glyph: '+1', legendKey: 'history.legend.pointT1' },
  'point-t2': { glyph: '+1', legendKey: 'history.legend.pointT2' },
  'point':    { glyph: '+1', legendKey: null },
  'set':      { glyph: '🏆', legendKey: 'history.legend.set' },
  'timeout':  { glyph: '⏸', legendKey: 'history.legend.timeout' },
  'serve':    { glyph: '⇄', legendKey: 'history.legend.serve' },
  'edit':     { glyph: '✎', legendKey: 'history.legend.edit' },
  'reset':    { glyph: '⟲', legendKey: 'history.legend.reset' },
  'undone':   { glyph: '↶', legendKey: 'history.legend.undone' },
  'other':    { glyph: '•', legendKey: null },
};

/**
 * Classifier mirror of ``app.match_report._chip_classifier``.
 *
 * Resolves the chip kind for an audit-record action+team pair. The
 * separate ``wasUndone`` flag lets callers mark a record as undone
 * without changing its semantic action — same convention the
 * match-report uses for paired records.
 */
export function classifyChip(
  action: string,
  team: 1 | 2 | undefined,
  wasUndone: boolean,
): ChipKind {
  if (action === 'add_point') {
    if (team === 1) return 'point-t1';
    if (team === 2) return 'point-t2';
    return 'point';
  }
  if (action === 'add_set') return 'set';
  if (action === 'add_timeout') return 'timeout';
  if (action === 'change_serve') return 'serve';
  if (action === 'set_score') return 'edit';
  if (action === 'reset') return 'reset';
  if (wasUndone) return 'undone';
  return 'other';
}
