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

const I18nContext = createContext<I18nContextValue | undefined>(undefined);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<string>(() => {
    try {
      const saved = localStorage.getItem('volley_lang');
      if (saved && translations[saved]) return saved;
    } catch (e) {
      console.warn('Failed to read language setting:', e);
    }
    const browserLang = navigator.language?.slice(0, 2);
    return translations[browserLang ?? ''] ? browserLang! : 'en';
  });

  const setLanguage = useCallback((l: string) => {
    setLang(l);
    try {
      localStorage.setItem('volley_lang', l);
    } catch (e) {
      console.warn('Failed to save language setting:', e);
    }
  }, []);

  const t = useCallback<Translate>(
    (key, params) => {
      let str = translations[lang]?.[key] ?? translations.en?.[key] ?? key;
      if (params) {
        Object.entries(params).forEach(([k, v]) => {
          str = str.replaceAll(`{${k}}`, () => String(v));
        });
      }
      return str;
    },
    [lang],
  );

  const value = useMemo<I18nContextValue>(
    () => ({ lang, setLanguage, t, languages: Object.keys(translations) }),
    [lang, setLanguage, t],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error('useI18n must be used within an I18nProvider');
  return ctx;
}
