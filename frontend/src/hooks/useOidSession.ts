import { useState, useCallback, type FormEvent } from 'react';
import { getScopedItem, removeScopedItem, type StorageScope } from '../storage/ScopedStorage';

function getInitialOid(storageScope: StorageScope): string {
  const params = new URLSearchParams(window.location.search);
  const urlOid = params.get('oid') || params.get('control');
  if (urlOid) return urlOid;
  try {
    return getScopedItem(storageScope, 'oid') || '';
  } catch {
    return '';
  }
}

export interface UseOidSessionResult {
  oid: string;
  setOid: (oid: string) => void;
  oidInput: string;
  setOidInput: (value: string) => void;
  handleInit: (e?: FormEvent<HTMLFormElement>) => void;
  handleLogout: () => void;
}

/**
 * OID selection state: URL-param / localStorage bootstrap, the init
 * form submit, and logout (which clears the persisted OID). The
 * persist-and-initialize side effect stays in ``App`` because it
 * needs ``initialize`` from ``useGameState(oid)``, which in turn
 * needs the ``oid`` this hook owns.
 */
export function useOidSession({
  onLogout,
  initialOid,
  storageScope,
}: {
  onLogout?: (() => void) | undefined;
  initialOid?: string | undefined;
  storageScope: StorageScope;
}): UseOidSessionResult {
  // Operator (shareable-link) mode seeds the session handle from the control
  // token so the board never shows the owner-only OID picker.
  const [oid, setOid] = useState<string>(() => initialOid || getInitialOid(storageScope));
  const [oidInput, setOidInput] = useState<string>(oid);

  const handleInit = useCallback(
    (e?: FormEvent<HTMLFormElement>) => {
      e?.preventDefault();
      if (oidInput.trim()) {
        setOid(oidInput.trim());
      }
    },
    [oidInput],
  );

  const handleLogout = useCallback(() => {
    try {
      removeScopedItem(storageScope, 'oid');
    } catch (e) {
      console.warn('Failed to remove OID:', e);
    }
    setOid('');
    setOidInput('');
    onLogout?.();
  }, [onLogout, storageScope]);

  return { oid, setOid, oidInput, setOidInput, handleInit, handleLogout };
}
