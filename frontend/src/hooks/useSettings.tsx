import { createContext, useContext, useState, useCallback, useEffect, useMemo, ReactNode } from 'react';
import { TEAM_A_COLOR, TEAM_B_COLOR } from '../theme';

const LS_PREFIX = 'volley_';

export interface Settings {
  darkMode: boolean;
  followTeamColors: boolean;
  showIcon: boolean;
  iconOpacity: number;
  autoSimple: boolean;
  autoSimpleOnTimeout: boolean;
  showPreview: boolean;
  selectedFont: string;
  team1BtnColor: string;
  team1BtnText: string;
  team2BtnColor: string;
  team2BtnText: string;
  autoHide: boolean;
  autoHideSeconds: number;
}

const DEFAULTS: Settings = {
  darkMode: true,
  followTeamColors: false,
  showIcon: false,
  iconOpacity: 50,
  autoSimple: false,
  autoSimpleOnTimeout: false,
  showPreview: true,
  selectedFont: 'Default',
  team1BtnColor: TEAM_A_COLOR,
  team1BtnText: '#ffffff',
  team2BtnColor: TEAM_B_COLOR,
  team2BtnText: '#ffffff',
  autoHide: false,
  autoHideSeconds: 5,
};

function readAll(): Settings {
  const result: Settings = { ...DEFAULTS };
  for (const key of Object.keys(DEFAULTS) as Array<keyof Settings>) {
    try {
      const v = localStorage.getItem(LS_PREFIX + key);
      if (v !== null) (result as unknown as Record<string, unknown>)[key] = JSON.parse(v);
    } catch { /* use default */ }
  }
  return result;
}

export type SetSetting = <K extends keyof Settings>(key: K, value: Settings[K]) => void;

export interface SettingsContextValue {
  settings: Settings;
  setSetting: SetSetting;
}

const SettingsContext = createContext<SettingsContextValue | undefined>(undefined);

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<Settings>(readAll);

  const setSetting = useCallback<SetSetting>((key, value) => {
    setSettings((prev) => {
      if (prev[key] === value) return prev;
      try {
        localStorage.setItem(LS_PREFIX + key, JSON.stringify(value));
      } catch (e) {
        console.warn('Failed to save setting ' + String(key) + ':', e);
      }
      return { ...prev, [key]: value };
    });
  }, []);

  useEffect(() => {
    function onStorage(e: StorageEvent) {
      if (e.key === null || e.key.startsWith(LS_PREFIX)) {
        setSettings(readAll());
      }
    }
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  useEffect(() => {
    document.documentElement.classList.toggle('light', !settings.darkMode);
  }, [settings.darkMode]);

  const value = useMemo(() => ({ settings, setSetting }), [settings, setSetting]);

  return (
    <SettingsContext.Provider value={value}>
      {children}
    </SettingsContext.Provider>
  );
}

export function useSettings(): SettingsContextValue {
  const ctx = useContext(SettingsContext);
  if (!ctx) throw new Error('useSettings must be used within a SettingsProvider');
  return ctx;
}

export { DEFAULTS as SETTINGS_DEFAULTS };
