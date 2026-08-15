import { useEffect, useRef } from 'react';
import type { ActionResponse } from '../api/board';
import { asString } from '../utils/coerce';

type Customization = Record<string, unknown>;

/**
 * Push the operator's UI language onto the overlay's customization so
 * OBS-embedded overlays (whose URL is fixed in the streaming app and
 * cannot carry ``?lang=``) follow language changes live. The ref
 * pins per-``lang`` attempts so a failing backend doesn't retry on
 * every parent re-render (only when the operator picks a new
 * language). Invariant: the control WS broadcasts ``state_update``
 * only, never ``customization_update`` — so a second operator's
 * PUT cannot bounce this effect into a ping-pong.
 *
 * The write goes through ``syncLocale`` (``useGameState``'s serialized
 * mutation queue) rather than calling the API directly: an unqueued
 * conditional PUT would carry the same revision as an in-flight point,
 * and whichever request reached the server's lock second would be
 * rejected with a 409 — dropping either the point or, because the pin
 * below is already set, this sync for good.
 */
export function useOverlayLocaleSync({
  oid,
  lang,
  customization,
  syncLocale,
  refreshCustomization,
}: {
  oid: string;
  lang: string;
  customization: Customization | null;
  syncLocale: (locale: string) => Promise<ActionResponse>;
  refreshCustomization: () => void;
}): void {
  const lastAttemptedLocaleRef = useRef<string | null>(null);
  const customizationLocale = asString(customization?.['locale']);
  useEffect(() => {
    if (!oid) return;
    const attemptKey = oid + ':' + lang;
    if (customizationLocale === lang) return;
    if (lastAttemptedLocaleRef.current === attemptKey) return;
    lastAttemptedLocaleRef.current = attemptKey;
    syncLocale(lang)
      .then((res) => {
        if (res.success) refreshCustomization();
        else console.warn('Failed to sync overlay locale:', res.message);
      })
      .catch((e) => {
        console.warn('Failed to sync overlay locale:', e);
      });
  }, [oid, lang, customizationLocale, syncLocale, refreshCustomization]);
}
