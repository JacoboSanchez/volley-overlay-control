import { useEffect, useRef } from 'react';
import * as api from '../api/board';
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
 */
export function useOverlayLocaleSync({
  oid,
  lang,
  customization,
  expectedRevision,
  refreshCustomization,
}: {
  oid: string;
  lang: string;
  customization: Customization | null;
  expectedRevision?: number | undefined;
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
    const update =
      expectedRevision === undefined
        ? api.updateCustomization(oid, { locale: lang })
        : api.updateCustomization(oid, { locale: lang }, expectedRevision);
    update
      .then(() => refreshCustomization())
      .catch((e) => {
        console.warn('Failed to sync overlay locale:', e);
      });
  }, [oid, lang, customizationLocale, expectedRevision, refreshCustomization]);
}
