import { useCallback, useMemo, useState } from 'react';

/** Multi-select state for a team list, shared by the user roster and the admin
 *  catalog. Selection is by team id so it survives re-sorting and filtering. */
export interface TeamSelection {
  has: (id: number) => boolean;
  size: number;
  ids: number[];
  toggle: (id: number) => void;
  replace: (ids: number[]) => void;
  clear: () => void;
}

export function useTeamSelection(): TeamSelection {
  const [sel, setSel] = useState<Set<number>>(new Set());

  const toggle = useCallback((id: number) => {
    setSel((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);
  const replace = useCallback((ids: number[]) => setSel(new Set(ids)), []);
  const clear = useCallback(() => setSel(new Set()), []);

  return useMemo(
    () => ({
      has: (id: number) => sel.has(id),
      size: sel.size,
      ids: [...sel],
      toggle,
      replace,
      clear,
    }),
    [sel, toggle, replace, clear],
  );
}
