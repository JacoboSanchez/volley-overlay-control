import {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  useMemo,
  ReactNode,
} from 'react';
import { TEAM_A_COLOR, TEAM_B_COLOR } from '../theme';
import { defaultKeyboardShortcutsEnabled } from './useKeyboardShortcuts';

const LS_PREFIX = 'volley_';

/**
 * Theme preference. ``'auto'`` follows the OS ``prefers-color-scheme``
 * media query and updates live as the OS preference changes. ``true``
 * forces dark mode; ``false`` forces light mode.
 */
export type ThemePreference = boolean | 'auto';

export interface Settings {
  darkMode: ThemePreference;
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
  /**
   * Haptic feedback toggle. When ``true`` the operator's device
   * vibrates briefly on confirmed double-tap-undo gestures and on
   * set / match / finished transitions. Defaults to ``false`` so a
   * fresh install doesn't surprise the operator with vibration on
   * the first scoring tap; the toggle in BehaviorSection opts in.
   * Devices without ``navigator.vibrate`` (desktop browsers, iOS
   * Safari pre-18.4) no-op silently regardless of the toggle.
   */
  haptics: boolean;
  /**
   * Whether the operator has dismissed the first-use gesture tour.
   * Persists across sessions so the coachmark only fires once per
   * device/profile by default. The Behavior section exposes a
   * "Replay tour" affordance that flips this back to ``false``.
   */
  gestureTourSeen: boolean;
  /**
   * Keyboard shortcuts for the scoreboard operator (A/B = add point,
   * Z = undo, 1/2 = serve, Q/P = timeout, Space = start, H = toggle
   * overlay, S = simple mode, ? = help). Default ON for fine-pointer
   * devices (mouse / keyboard), OFF for coarse-pointer (touch-only)
   * so accidental keystrokes on tablets with a screen keyboard don't
   * score points.
   */
  keyboardShortcuts: boolean;
  /**
   * Feature flag for the "set summary overlay" — a recap panel that
   * replaces the scoreboard between sets in OBS. Default OFF: the
   * toggle button is hidden in ``ControlButtons`` until the operator
   * opts in from the config panel. Existing setups don't get a
   * surprise extra button.
   */
  setSummaryEnabled: boolean;
}

const DEFAULTS: Settings = {
  darkMode: 'auto',
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
  haptics: false,
  gestureTourSeen: false,
  keyboardShortcuts: defaultKeyboardShortcutsEnabled(),
  setSummaryEnabled: false,
};

/**
 * Resolve a :class:`ThemePreference` to a concrete boolean.
 * ``'auto'`` consults ``prefers-color-scheme`` (defaulting to dark when
 * the media query is unavailable, e.g. SSR or test environments).
 */
export function resolveDarkMode(pref: ThemePreference): boolean {
  if (pref === 'auto') {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return true;
    }
    return window.matchMedia('(prefers-color-scheme: dark)').matches;
  }
  return pref;
}

function readAll(): Settings {
  const result: Settings = { ...DEFAULTS };
  for (const key of Object.keys(DEFAULTS) as Array<keyof Settings>) {
    try {
      const v = localStorage.getItem(LS_PREFIX + key);
      // JSON.parse returns ``any``; we route through Object.assign rather
      // than a mutating index assignment so we avoid the ``as unknown as``
      // double-cast the previous version needed to bypass keyof Settings's
      // write-side narrowness.
      if (v !== null) Object.assign(result, { [key]: JSON.parse(v) });
    } catch {
      /* use default */
    }
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
    const apply = () => {
      const isDark = resolveDarkMode(settings.darkMode);
      document.documentElement.classList.toggle('light', !isDark);
    };
    apply();

    if (
      settings.darkMode !== 'auto' ||
      typeof window === 'undefined' ||
      typeof window.matchMedia !== 'function'
    ) {
      return;
    }

    const mql = window.matchMedia('(prefers-color-scheme: dark)');
    mql.addEventListener('change', apply);
    return () => mql.removeEventListener('change', apply);
  }, [settings.darkMode]);

  const value = useMemo(() => ({ settings, setSetting }), [settings, setSetting]);

  return <SettingsContext.Provider value={value}>{children}</SettingsContext.Provider>;
}

export function useSettings(): SettingsContextValue {
  const ctx = useContext(SettingsContext);
  if (!ctx) throw new Error('useSettings must be used within a SettingsProvider');
  return ctx;
}

export { DEFAULTS as SETTINGS_DEFAULTS };
