import { createContext, useContext, useState, useCallback, useMemo, ReactNode } from 'react';

import { translations } from './i18n/translations';

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

const STORAGE_KEY = 'volley_lang';

function translate(lang: string, key: string, params?: TranslateParams): string {
  let str = translations[lang]?.[key] ?? translations.en?.[key] ?? key;
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      str = str.replaceAll(`{${k}}`, () => String(v));
    });
  }
  return str;
}

function detectInitialLang(): string {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
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
  const [lang, setLang] = useState<string>(detectInitialLang);

  const setLanguage = useCallback((l: string) => {
    setLang(l);
    try {
      localStorage.setItem(STORAGE_KEY, l);
    } catch (e) {
      console.warn('Failed to save language setting:', e);
    }
  }, []);

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
