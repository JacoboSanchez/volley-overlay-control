import { useCallback, useEffect, useRef, useState } from 'react';
import type { ConfigModel } from '../TeamCard';

export interface ConfigModelState {
  /** The staged edit model — what Save will persist. */
  model: ConfigModel;
  isDirty: boolean;
  /** Transient "Saved ✓" confirmation, cleared on a timer or the next edit. */
  justSaved: boolean;
  /** Stage one field edit. */
  updateField: (key: string, value: unknown) => void;
  /** Shallow-merge a patch (a preset load) into the staged model. */
  applyPatch: (patch: ConfigModel) => void;
  /** Called after a successful save: drops the dirty flag, shows "Saved ✓". */
  markSaved: () => void;
}

const JUST_SAVED_MS = 2500;

/**
 * The config panel's form model: the staged copy of `customization`, its
 * dirty flag, and the transient post-save confirmation.
 *
 * Dirtiness is a flag toggled by the mutation paths rather than a comparison
 * of `model` against `customization`: the form has many fields and takes a
 * `setModel` on every keystroke, so the double-`JSON.stringify` the previous
 * version used was O(n) in depth and key count on every render.
 */
export function useConfigModel(customization: ConfigModel | null | undefined): ConfigModelState {
  const [model, setModel] = useState<ConfigModel>(() => ({ ...(customization ?? {}) }));
  const [isDirty, setIsDirty] = useState(false);
  const [justSaved, setJustSaved] = useState(false);
  const justSavedTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (customization) {
      setModel({ ...customization });
      setIsDirty(false);
    }
  }, [customization]);

  useEffect(
    () => () => {
      if (justSavedTimerRef.current) clearTimeout(justSavedTimerRef.current);
    },
    [],
  );

  const clearJustSaved = useCallback(() => {
    if (justSavedTimerRef.current) {
      clearTimeout(justSavedTimerRef.current);
      justSavedTimerRef.current = null;
    }
    setJustSaved(false);
  }, []);

  const updateField = useCallback(
    (key: string, value: unknown) => {
      setModel((m) => ({ ...m, [key]: value }));
      setIsDirty(true);
      clearJustSaved();
    },
    [clearJustSaved],
  );

  // A preset load shares the staging semantics of a direct field edit:
  // shallow-merge, mark dirty, and let Save persist it. That avoids racing
  // the operator's own unsaved changes.
  const applyPatch = useCallback(
    (patch: ConfigModel) => {
      clearJustSaved();
      setModel((m) => ({ ...m, ...patch }));
      setIsDirty(true);
    },
    [clearJustSaved],
  );

  const markSaved = useCallback(() => {
    setIsDirty(false);
    setJustSaved(true);
    if (justSavedTimerRef.current) clearTimeout(justSavedTimerRef.current);
    justSavedTimerRef.current = setTimeout(() => setJustSaved(false), JUST_SAVED_MS);
  }, []);

  return { model, isDirty, justSaved, updateField, applyPatch, markSaved };
}
