/** Per-overlay share links and the helpers shared by the board Share dialog
 *  and the Config "Links" section. */
export interface ShareLinks {
  control?: string;
  overlay?: string;
  preview?: string;
  follow?: string;
  latest_match_report?: string;
  match_history?: string;
}

/** Render order for the standard link set. */
export const LINK_KEYS: Array<keyof ShareLinks> = [
  'control',
  'overlay',
  'preview',
  'follow',
  'latest_match_report',
  'match_history',
];

// Keys whose URL targets a locale-aware HTML surface (the match report, the
// matches index, and the public spectator/follow page). We append the
// operator's selected app locale as ``?lang=<code>`` so the spectator sees the
// same language the operator was using when they shared the link, rather than
// whatever ``Accept-Language`` the spectator's browser advertises.
export const LOCALE_AWARE_KEYS: ReadonlySet<keyof ShareLinks> = new Set([
  'follow',
  'latest_match_report',
  'match_history',
]);

/** Append the operator's app locale as ``?lang=`` to a locale-aware URL. */
export function withLang(url: string, lang: string): string {
  try {
    const parsed = new URL(url, window.location.origin);
    parsed.searchParams.set('lang', lang);
    return parsed.toString();
  } catch {
    // Malformed URL — leave it untouched rather than corrupt it.
    return url;
  }
}
