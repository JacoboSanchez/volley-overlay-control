/**
 * Copy text to the clipboard, falling back to a hidden-textarea +
 * ``execCommand('copy')`` for browsers / insecure contexts where the async
 * Clipboard API is unavailable. Best-effort: never throws, so callers can
 * fire-and-forget (the source field usually stays selectable for manual copy).
 */
export async function writeToClipboard(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text);
    return;
  } catch {
    // Async Clipboard API unavailable/denied — fall through to the legacy path.
  }
  try {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
  } catch {
    // Nothing more we can do — leave the caller's field selectable.
  }
}
