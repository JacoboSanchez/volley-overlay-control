import {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  useMemo,
  type ReactNode,
} from 'react';

import { translations } from './i18n/translations';
import { getScopedItem, setScopedItem, useStorageScope } from './storage/ScopedStorage';

export type TranslateParams = Record<string, string | number>;
export type Translate = (key: string, params?: TranslateParams) => string;

export interface I18nContextValue {
  lang: string;
  setLanguage: (l: string) => void;
  t: Translate;
  languages: string[];
}

/** Human-readable names for each supported UI language, keyed by code. Shared
 *  by every language picker (board config + account settings). */
export const LANGUAGE_NAMES: Record<string, string> = {
  en: 'English',
  es: 'Español',
  pt: 'Português',
  it: 'Italiano',
  fr: 'Français',
  de: 'Deutsch',
};

const STORAGE_NAME = 'lang';

function translate(lang: string, key: string, params?: TranslateParams): string {
  let str = translations[lang]?.[key] ?? translations.en?.[key] ?? key;
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      str = str.replaceAll(`{${k}}`, () => String(v));
    });
  }
  return str;
}

function detectInitialLang(scope: ReturnType<typeof useStorageScope>): string {
  try {
    const saved = getScopedItem(scope, STORAGE_NAME);
    if (saved && translations[saved]) return saved;
  } catch (e) {
    console.warn('Failed to read language setting:', e);
  }
  const browserLang =
    typeof navigator !== 'undefined' ? navigator.language?.slice(0, 2) : undefined;
  return browserLang && translations[browserLang] ? browserLang : 'en';
}

const I18nContext = createContext<I18nContextValue | undefined>(undefined);

export function I18nProvider({ children }: { children: ReactNode }) {
  const storageScope = useStorageScope();
  const [lang, setLang] = useState<string>(() => detectInitialLang(storageScope));

  useEffect(() => {
    setLang(detectInitialLang(storageScope));
  }, [storageScope]);

  const setLanguage = useCallback(
    (l: string) => {
      setLang(l);
      try {
        setScopedItem(storageScope, STORAGE_NAME, l);
      } catch (e) {
        console.warn('Failed to save language setting:', e);
      }
    },
    [storageScope],
  );

  const t = useCallback<Translate>((key, params) => translate(lang, key, params), [lang]);

  const value = useMemo<I18nContextValue>(
    () => ({ lang, setLanguage, t, languages: Object.keys(translations) }),
    [lang, setLanguage, t],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

/** Active language + translator. Outside an I18nProvider (e.g. an isolated
 *  component test) it falls back to a read-only English context so callers can
 *  use ``t`` unconditionally without crashing. */
export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (ctx) return ctx;
  return {
    lang: 'en',
    setLanguage: () => {},
    t: (key, params) => translate('en', key, params),
    languages: Object.keys(translations),
  };
}
