import { useState, useCallback, FormEvent } from 'react';

function getInitialOid(): string {
  const params = new URLSearchParams(window.location.search);
  const urlOid = params.get('oid') || params.get('control');
  if (urlOid) return urlOid;
  try {
    return localStorage.getItem('volley_oid') || '';
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
export function useOidSession(
  { onLogout, initialOid }: { onLogout?: () => void; initialOid?: string } = {},
): UseOidSessionResult {
  // Operator (shareable-link) mode seeds the session handle from the control
  // token so the board never shows the owner-only OID picker.
  const [oid, setOid] = useState<string>(() => initialOid || getInitialOid());
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
      localStorage.removeItem('volley_oid');
    } catch (e) {
      console.warn('Failed to remove OID:', e);
    }
    setOid('');
    setOidInput('');
    onLogout?.();
  }, [onLogout]);

  return { oid, setOid, oidInput, setOidInput, handleInit, handleLogout };
}
