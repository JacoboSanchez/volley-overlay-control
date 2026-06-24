import type { RefObject } from 'react';
import type { TeamOut } from '../../api/client';

/** Defaults for a brand-new team's colours (matches the scoreboard picker). */
export const DEFAULT_COLOR = '#1565c0';
export const DEFAULT_TEXT_COLOR = '#ffffff';

/** Lists shorter than this don't get a filter box — it would just be noise. */
export const FILTER_THRESHOLD = 8;

/** Coerce a stored colour to a `#rrggbb` string, falling back when it's blank
 *  or in some other format the picker can't render. */
export function hex(value: string | null | undefined, fallback: string): string {
  return value && /^#[0-9a-fA-F]{6}$/.test(value) ? value : fallback;
}

/** Case-insensitive substring filter on team name. Generic so it works on the
 *  catalog rows and on a group's member list alike. */
export function filterTeams<T extends { name: string }>(list: T[], query: string): T[] {
  const needle = query.trim().toLowerCase();
  return needle ? list.filter((team) => team.name.toLowerCase().includes(needle)) : list;
}

/** A team the user owns (custom) vs. one from the global catalog. */
export function isCustom(team: TeamOut): boolean {
  return !team.is_global;
}

/** Keep the row currently being edited (`editingId`) visible even when the
 *  active filter would hide it, so typing in the filter box never unmounts an
 *  open inline editor and silently discards the in-progress edit. */
export function withPinnedEdit(
  shown: TeamOut[],
  all: TeamOut[],
  editingId: number | null,
): TeamOut[] {
  if (editingId == null || shown.some((team) => team.id === editingId)) return shown;
  const pinned = all.find((team) => team.id === editingId);
  return pinned ? [...shown, pinned] : shown;
}

/** Move keyboard focus back to a list's select-all checkbox after a bulk action
 *  clears the selection and unmounts the bar that held focus (else focus drops
 *  to <body>). rAF so the focus target has re-rendered first. */
export function restoreFocus(ref: RefObject<HTMLInputElement | null>): void {
  requestAnimationFrame(() => ref.current?.focus());
}
