import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { act, render } from '@testing-library/react';
import { useEffect } from 'react';
import {
  SettingsProvider,
  useSettings,
  resolveDarkMode,
  ThemePreference,
} from '../hooks/useSettings';

function setMatchMedia(matches: boolean) {
  const listeners = new Set<(e: MediaQueryListEvent) => void>();
  const mql = {
    matches,
    media: '(prefers-color-scheme: dark)',
    onchange: null,
    addEventListener: (_: string, l: (e: MediaQueryListEvent) => void) => {
      listeners.add(l);
    },
    removeEventListener: (_: string, l: (e: MediaQueryListEvent) => void) => {
      listeners.delete(l);
    },
    addListener: () => undefined,
    removeListener: () => undefined,
    dispatchEvent: () => false,
  };
  vi.stubGlobal('matchMedia', vi.fn().mockReturnValue(mql));
  return {
    mql,
    fireChange(newValue: boolean) {
      mql.matches = newValue;
      listeners.forEach((l) => l({ matches: newValue } as MediaQueryListEvent));
    },
  };
}

describe('resolveDarkMode', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('returns the boolean as-is for explicit preferences', () => {
    expect(resolveDarkMode(true)).toBe(true);
    expect(resolveDarkMode(false)).toBe(false);
  });

  it('consults matchMedia when preference is auto', () => {
    setMatchMedia(true);
    expect(resolveDarkMode('auto')).toBe(true);

    setMatchMedia(false);
    expect(resolveDarkMode('auto')).toBe(false);
  });
});

describe('SettingsProvider theme application', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.classList.remove('light');
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    document.documentElement.classList.remove('light');
  });

  function ThemeProbe() {
    const { settings } = useSettings();
    useEffect(() => {
      // Force re-render on settings change so we can observe DOM.
    }, [settings]);
    return null;
  }

  it('applies the .light class when OS prefers light and pref is auto', () => {
    setMatchMedia(false); // OS reports light.
    render(
      <SettingsProvider>
        <ThemeProbe />
      </SettingsProvider>,
    );
    expect(document.documentElement.classList.contains('light')).toBe(true);
  });

  it('drops the .light class when OS switches to dark', () => {
    const mm = setMatchMedia(false);
    render(
      <SettingsProvider>
        <ThemeProbe />
      </SettingsProvider>,
    );
    expect(document.documentElement.classList.contains('light')).toBe(true);

    act(() => mm.fireChange(true));
    expect(document.documentElement.classList.contains('light')).toBe(false);
  });

  it('explicit preference wins over OS preference', () => {
    setMatchMedia(true); // OS dark.
    localStorage.setItem('volley_darkMode', JSON.stringify(false));
    render(
      <SettingsProvider>
        <ThemeProbe />
      </SettingsProvider>,
    );
    expect(document.documentElement.classList.contains('light')).toBe(true);
  });

  it('explicit dark preference adds no .light class', () => {
    setMatchMedia(false); // OS light.
    localStorage.setItem('volley_darkMode', JSON.stringify(true));
    render(
      <SettingsProvider>
        <ThemeProbe />
      </SettingsProvider>,
    );
    expect(document.documentElement.classList.contains('light')).toBe(false);
  });

  it('reads "auto" from localStorage', () => {
    setMatchMedia(false);
    const stored: ThemePreference = 'auto';
    localStorage.setItem('volley_darkMode', JSON.stringify(stored));
    render(
      <SettingsProvider>
        <ThemeProbe />
      </SettingsProvider>,
    );
    expect(document.documentElement.classList.contains('light')).toBe(true);
  });
});
