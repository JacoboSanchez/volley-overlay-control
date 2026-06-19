import { ReactElement, ReactNode } from 'react';
import { render, RenderOptions } from '@testing-library/react';
import { I18nProvider } from '../i18n';
import { SettingsProvider } from '../hooks/useSettings';
import type { GameState } from '../api/client';

// Use the ``wrapper`` option (rather than wrapping ``ui`` inline) so the
// providers are re-applied by ``rerender`` too — otherwise a rerender drops
// the I18n/Settings context and any component calling ``useI18n`` throws.
export function renderWithI18n(ui: ReactElement, options: Omit<RenderOptions, 'wrapper'> = {}) {
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <I18nProvider>
      <SettingsProvider>{children}</SettingsProvider>
    </I18nProvider>
  );
  return render(ui, { wrapper: Wrapper, ...options });
}

export const mockGameState: GameState = {
  team_1: {
    sets: 1,
    timeouts: 1,
    timeouts_by_set: { set_1: 0, set_2: 1 },
    serving: true,
    scores: { set_1: 25, set_2: 12 },
  },
  team_2: {
    sets: 0,
    timeouts: 0,
    timeouts_by_set: { set_1: 0, set_2: 0 },
    serving: false,
    scores: { set_1: 20, set_2: 10 },
  },
  visible: true,
  simple_mode: false,
  match_finished: false,
  current_set: 1,
  serve: '1',
  config: { sets_limit: 5, points_limit: 25 },
  can_undo: false,
  set_summary: false,
  set_summary_set_num: null,
  set_summary_style: 'brand_ledger',
  sides_swapped: false,
  auto_swap_sides: false,
};

export const mockCustomization = {
  'Team 1 Name': 'Home',
  'Team 1 Color': '#0000ff',
  'Team 1 Text Color': '#ffffff',
  'Team 1 Logo': '',
  'Team 2 Name': 'Away',
  'Team 2 Color': '#ff0000',
  'Team 2 Text Color': '#ffffff',
  'Team 2 Logo': '',
  Logos: 'true',
  Gradient: 'false',
  'Color 1': '#2a2f35',
  'Text Color 1': '#ffffff',
  'Color 2': '#ffffff',
  'Text Color 2': '#2a2f35',
  Height: 10,
  Width: 30,
  'Left-Right': -33,
  'Up-Down': -41.1,
};
