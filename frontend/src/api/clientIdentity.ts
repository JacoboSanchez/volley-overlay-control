/** Ephemeral, tab-scoped identity used for presence and audit attribution. */

const ID_KEY = 'volley_client_id';
const LABEL_KEY = 'volley_client_label';

let memoryId: string | null = null;
let memoryLabel: string | null = null;
const VALID_ID = /^[A-Za-z0-9._:-]{8,64}$/;

function cleanLabel(label: string | null | undefined): string | null {
  const cleaned = Array.from(label?.trim() ?? '')
    .filter((character) => {
      const codePoint = character.codePointAt(0) ?? 0;
      return codePoint >= 32 && codePoint !== 127;
    })
    .join('')
    .slice(0, 40);
  return cleaned || null;
}

function mintId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `tab-${crypto.randomUUID()}`;
  }
  return `tab-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 14)}`;
}

export function getClientId(): string {
  if (memoryId) return memoryId;
  try {
    const stored = sessionStorage.getItem(ID_KEY);
    if (stored && VALID_ID.test(stored)) return (memoryId = stored);
  } catch {
    // Sandboxed/private browsers may deny sessionStorage; memory still keeps
    // the id stable for this loaded tab.
  }
  memoryId = mintId();
  try {
    sessionStorage.setItem(ID_KEY, memoryId);
  } catch {
    /* memory fallback is sufficient */
  }
  return memoryId;
}

export function getClientLabel(): string | null {
  if (memoryLabel) return memoryLabel;
  try {
    memoryLabel = cleanLabel(sessionStorage.getItem(LABEL_KEY));
  } catch {
    /* optional label stays absent */
  }
  return memoryLabel;
}

export function setClientLabel(label: string | null): void {
  const cleaned = cleanLabel(label);
  memoryLabel = cleaned;
  try {
    if (cleaned) sessionStorage.setItem(LABEL_KEY, cleaned);
    else sessionStorage.removeItem(LABEL_KEY);
  } catch {
    /* optional label remains memory-only */
  }
}

export function clientHeaders(): Record<string, string> {
  const headers = { 'X-Client-ID': getClientId() };
  const label = getClientLabel();
  return label ? { ...headers, 'X-Client-Label': label } : headers;
}
