import React, { createContext, useContext, useState, useCallback, useEffect } from 'react';
import { TEAM_A_COLOR, TEAM_B_COLOR } from '../theme';

const LS_PREFIX = 'volley_';

const DEFAULTS = {
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

function readAll() {
  const result = { ...DEFAULTS };
  for (const key of Object.keys(DEFAULTS)) {
    try {
      const v = localStorage.getItem(LS_PREFIX + key);
      if (v !== null) result[key] = JSON.parse(v);
    } catch { /* use default */ }
  }
  return result;
}

const SettingsContext = createContext();

export function SettingsProvider({ children }) {
  const [settings, setSettings] = useState(readAll);

  const setSetting = useCallback((key, value) => {
    setSettings((prev) => {
      if (prev[key] === value) return prev;
      try {
        localStorage.setItem(LS_PREFIX + key, JSON.stringify(value));
      } catch (e) {
        console.warn('Failed to save setting ' + key + ':', e);
      }
      return { ...prev, [key]: value };
    });
  }, []);

  // Cross-tab sync
  useEffect(() => {
    function onStorage(e) {
      if (e.key === null || e.key.startsWith(LS_PREFIX)) {
        setSettings(readAll());
      }
    }
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  // Sync dark mode class on <html>
  useEffect(() => {
    document.documentElement.classList.toggle('light', !settings.darkMode);
  }, [settings.darkMode]);

  return (
    <SettingsContext.Provider value={{ settings, setSetting }}>
      {children}
    </SettingsContext.Provider>
  );
}

export function useSettings() {
  return useContext(SettingsContext);
}

export { DEFAULTS as SETTINGS_DEFAULTS };
