/** Ephemeral, tab-scoped identity used for presence and audit attribution. */

const ID_KEY = 'volley_client_id';
const LABEL_KEY = 'volley_client_label';
// Set while a live tab is using the stored id. Duplicating a tab (or opening
// one from a same-origin link) copies sessionStorage wholesale, so the copy
// would otherwise reuse the opener's id — and ``WSHub.presence()``
// deduplicates by ``client_id``, reporting two real controllers as one and
// attributing both tabs' audit rows to the same identity. The claim is
// released on ``pagehide`` so a plain reload still keeps its id.
const CLAIM_KEY = 'volley_client_id_live';

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

/** Free the stored id when this page goes away, so the next load of *this*
 *  tab (a reload) may take it back while a duplicate cannot. */
function releaseClaimOnUnload(): void {
  if (typeof window === 'undefined' || typeof window.addEventListener !== 'function') return;
  window.addEventListener('pagehide', () => {
    try {
      sessionStorage.removeItem(CLAIM_KEY);
    } catch {
      /* nothing to release */
    }
  });
}

export function getClientId(): string {
  if (memoryId) return memoryId;
  let stored: string | null = null;
  let claimed = false;
  try {
    stored = sessionStorage.getItem(ID_KEY);
    // A tab that was duplicated inherits the claim of the tab it came from;
    // one that was reloaded finds it released by the handler below.
    claimed = sessionStorage.getItem(CLAIM_KEY) === '1';
  } catch {
    // Sandboxed/private browsers may deny sessionStorage; memory still keeps
    // the id stable for this loaded tab.
  }
  memoryId = stored && VALID_ID.test(stored) && !claimed ? stored : mintId();
  try {
    sessionStorage.setItem(ID_KEY, memoryId);
    sessionStorage.setItem(CLAIM_KEY, '1');
  } catch {
    /* memory fallback is sufficient */
  }
  releaseClaimOnUnload();
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
