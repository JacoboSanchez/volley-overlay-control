import { useEffect, useRef } from 'react';

type Team = 1 | 2;

export interface KeyboardShortcutHandlers {
  onAddPoint?: (team: Team) => void;
  onUndoLast?: () => void;
  onChangeServe?: (team: Team) => void;
  onAddTimeout?: (team: Team) => void;
  onStartMatch?: () => void;
  onToggleVisibility?: () => void;
  onToggleSimpleMode?: () => void;
  onOpenHelp?: () => void;
}

export interface UseKeyboardShortcutsOptions extends KeyboardShortcutHandlers {
  enabled: boolean;
}

/**
 * Map a `KeyboardEvent` to an abstract shortcut name. Returns ``null``
 * when the key isn't bound. Match is case-insensitive on letters.
 *
 * Centralising the mapping (rather than spreading ``key === '…'``
 * checks across the handler) lets the help modal render the same
 * table from a single source of truth.
 */
export const SHORTCUT_BINDINGS = {
  pointTeam1: ['a', 'A'],
  pointTeam2: ['b', 'B'],
  undo: ['z', 'Z'],
  serveTeam1: ['1'],
  serveTeam2: ['2'],
  timeoutTeam1: ['q', 'Q'],
  timeoutTeam2: ['p', 'P'],
  startMatch: [' '],
  toggleVisibility: ['h', 'H'],
  toggleSimple: ['s', 'S'],
  openHelp: ['?'],
} as const;

export type ShortcutName = keyof typeof SHORTCUT_BINDINGS;

function findShortcut(key: string): ShortcutName | null {
  for (const name of Object.keys(SHORTCUT_BINDINGS) as ShortcutName[]) {
    if ((SHORTCUT_BINDINGS[name] as readonly string[]).includes(key)) {
      return name;
    }
  }
  return null;
}

/**
 * Returns ``true`` when the keyboard event originated from an editable
 * element (input, textarea, contenteditable). Shortcuts must be
 * suppressed there so the operator can still type in dialogs and the
 * OID field.
 */
function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true;
  if (target.isContentEditable) return true;
  return false;
}

/**
 * Keyboard shortcuts for the scoreboard operator. Disabled by default
 * on touch-only devices via the ``enabled`` flag (see
 * ``useSettings.keyboardShortcuts``).
 *
 * Bindings (defaults):
 *   A / B  — add point for Team 1 / Team 2
 *   Z      — undo last action
 *   1 / 2  — change serve to Team 1 / Team 2
 *   Q / P  — timeout for Team 1 / Team 2
 *   Space  — start match (only when pending)
 *   H      — toggle overlay visibility
 *   S      — toggle simple mode
 *   ?      — open shortcuts help modal
 *
 * Shortcuts are suppressed when the user is typing in an input/textarea
 * or when a modal that owns focus is open (handled by the caller via
 * ``enabled``).
 */
export function useKeyboardShortcuts({
  enabled,
  onAddPoint,
  onUndoLast,
  onChangeServe,
  onAddTimeout,
  onStartMatch,
  onToggleVisibility,
  onToggleSimpleMode,
  onOpenHelp,
}: UseKeyboardShortcutsOptions): void {
  const handlersRef = useRef<KeyboardShortcutHandlers>({});
  handlersRef.current = {
    onAddPoint,
    onUndoLast,
    onChangeServe,
    onAddTimeout,
    onStartMatch,
    onToggleVisibility,
    onToggleSimpleMode,
    onOpenHelp,
  };

  useEffect(() => {
    if (!enabled) return undefined;

    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      if (isEditableTarget(e.target)) return;
      if (e.repeat) return;

      const name = findShortcut(e.key);
      if (!name) return;

      const h = handlersRef.current;
      switch (name) {
        case 'pointTeam1':
          if (h.onAddPoint) { e.preventDefault(); h.onAddPoint(1); }
          break;
        case 'pointTeam2':
          if (h.onAddPoint) { e.preventDefault(); h.onAddPoint(2); }
          break;
        case 'undo':
          if (h.onUndoLast) { e.preventDefault(); h.onUndoLast(); }
          break;
        case 'serveTeam1':
          if (h.onChangeServe) { e.preventDefault(); h.onChangeServe(1); }
          break;
        case 'serveTeam2':
          if (h.onChangeServe) { e.preventDefault(); h.onChangeServe(2); }
          break;
        case 'timeoutTeam1':
          if (h.onAddTimeout) { e.preventDefault(); h.onAddTimeout(1); }
          break;
        case 'timeoutTeam2':
          if (h.onAddTimeout) { e.preventDefault(); h.onAddTimeout(2); }
          break;
        case 'startMatch':
          if (h.onStartMatch) { e.preventDefault(); h.onStartMatch(); }
          break;
        case 'toggleVisibility':
          if (h.onToggleVisibility) { e.preventDefault(); h.onToggleVisibility(); }
          break;
        case 'toggleSimple':
          if (h.onToggleSimpleMode) { e.preventDefault(); h.onToggleSimpleMode(); }
          break;
        case 'openHelp':
          if (h.onOpenHelp) { e.preventDefault(); h.onOpenHelp(); }
          break;
      }
    };

    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [enabled]);
}

/**
 * Heuristic for the default value of ``settings.keyboardShortcuts``.
 * Coarse pointers (touch-only) get OFF, anything else gets ON.
 */
export function defaultKeyboardShortcutsEnabled(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return true;
  }
  try {
    return !window.matchMedia('(pointer: coarse)').matches;
  } catch {
    return true;
  }
}
