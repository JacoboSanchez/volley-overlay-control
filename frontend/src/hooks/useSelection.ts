import { useCallback, useMemo, useState } from 'react';

/**
 * Multi-select state for a list, keyed by whatever identifies a row (numeric
 * team ids, string match ids) so the selection survives re-sorting, filtering
 * and paging.
 *
 * The subset helpers all take the ids currently on screen, which is what every
 * "select all" header checkbox actually means — the visible page, not the whole
 * listing.
 */
export interface Selection<K> {
  has: (id: K) => boolean;
  size: number;
  ids: K[];
  toggle: (id: K) => void;
  /** Add every id in `ids` to the selection. */
  add: (ids: readonly K[]) => void;
  /** Drop every id in `ids` from the selection. */
  remove: (ids: readonly K[]) => void;
  /** Select all of `ids`, or drop them all when they are already selected. */
  toggleAll: (ids: readonly K[]) => void;
  /** True when `ids` is non-empty and every one of them is selected. */
  allSelected: (ids: readonly K[]) => boolean;
  /** True when at least one of `ids` is selected. */
  someSelected: (ids: readonly K[]) => boolean;
  /** `ids` filtered down to the selected ones, in the order given. */
  selectedAmong: (ids: readonly K[]) => K[];
  replace: (ids: readonly K[]) => void;
  clear: () => void;
}

export function useSelection<K extends string | number>(): Selection<K> {
  const [sel, setSel] = useState<Set<K>>(new Set());

  const toggle = useCallback((id: K) => {
    setSel((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);
  const add = useCallback((ids: readonly K[]) => {
    setSel((prev) => {
      const next = new Set(prev);
      for (const id of ids) next.add(id);
      return next;
    });
  }, []);
  const remove = useCallback((ids: readonly K[]) => {
    setSel((prev) => {
      const next = new Set(prev);
      for (const id of ids) next.delete(id);
      return next;
    });
  }, []);
  const toggleAll = useCallback((ids: readonly K[]) => {
    setSel((prev) => {
      const next = new Set(prev);
      // "All selected" is the state the checkbox is showing, so recompute it
      // from `prev` rather than trusting a value captured a render ago.
      const all = ids.length > 0 && ids.every((id) => prev.has(id));
      for (const id of ids) {
        if (all) next.delete(id);
        else next.add(id);
      }
      return next;
    });
  }, []);
  const replace = useCallback((ids: readonly K[]) => setSel(new Set(ids)), []);
  const clear = useCallback(() => setSel(new Set()), []);

  return useMemo(
    () => ({
      has: (id: K) => sel.has(id),
      size: sel.size,
      ids: [...sel],
      toggle,
      add,
      remove,
      toggleAll,
      allSelected: (ids: readonly K[]) => ids.length > 0 && ids.every((id) => sel.has(id)),
      someSelected: (ids: readonly K[]) => ids.some((id) => sel.has(id)),
      selectedAmong: (ids: readonly K[]) => ids.filter((id) => sel.has(id)),
      replace,
      clear,
    }),
    [sel, toggle, add, remove, toggleAll, replace, clear],
  );
}
