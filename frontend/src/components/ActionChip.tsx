import { CHIP_CATALOGUE, classifyChip, type ChipKind } from '../utils/chipCatalogue';

export interface ActionChipProps {
  /**
   * Pre-classified kind. When omitted, ``action`` + ``team`` +
   * ``wasUndone`` are passed through ``classifyChip``. Allowing both
   * shapes keeps the component usable in compact contexts (drawer
   * row), in legend rows (where the kind is the only input) and in
   * future test fixtures.
   */
  kind?: ChipKind;
  /** Audit record action when ``kind`` is omitted. */
  action?: string;
  /** Team that owns the action when ``kind`` is omitted. */
  team?: 1 | 2;
  /** Whether the record was reversed by a follow-up undo. */
  wasUndone?: boolean;
  /**
   * When ``true`` the chip renders only the coloured glyph cell —
   * useful for legend rows where the descriptive label is provided
   * by the surrounding markup. Defaults to ``false`` (full chip
   * with glyph + label slot).
   */
  glyphOnly?: boolean;
  /**
   * Optional label rendered next to the glyph. Ignored when
   * ``glyphOnly`` is ``true``.
   */
  label?: string;
}

/**
 * Tiny chip showing the per-action accent + glyph used by both the
 * post-match HTML report and the live operator drawer. The colour
 * palette comes from ``frontend/src/utils/chipCatalogue.ts`` which
 * mirrors ``app.match_report._CHIP_CATALOGUE`` so the operator and
 * the spectator see the same palette.
 */
export default function ActionChip({
  kind,
  action,
  team,
  wasUndone = false,
  glyphOnly = false,
  label,
}: ActionChipProps) {
  const resolvedKind: ChipKind = kind ?? classifyChip(action ?? '', team, wasUndone);
  const meta = CHIP_CATALOGUE[resolvedKind];

  return (
    <span
      className={`action-chip action-chip-${resolvedKind}`}
      data-kind={resolvedKind}
      data-testid="action-chip"
    >
      <span className={`chip-glyph chip-glyph-${resolvedKind}`} aria-hidden="true">
        {meta.glyph}
      </span>
      {!glyphOnly && label != null && <span className="action-chip-label">{label}</span>}
    </span>
  );
}
