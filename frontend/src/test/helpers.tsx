import { ReactElement } from 'react';
import { render, RenderOptions } from '@testing-library/react';
import { I18nProvider } from '../i18n';
import { SettingsProvider } from '../hooks/useSettings';

export function renderWithI18n(ui: ReactElement, options: Omit<RenderOptions, 'wrapper'> = {}) {
  return render(
    <I18nProvider>
      <SettingsProvider>
        {ui}
      </SettingsProvider>
    </I18nProvider>,
    options
  );
}

export const mockGameState = {
  team_1: {
    sets: 1,
    timeouts: 1,
    serving: true,
    scores: { set_1: 25, set_2: 12 },
  },
  team_2: {
    sets: 0,
    timeouts: 0,
    serving: false,
    scores: { set_1: 20, set_2: 10 },
  },
  visible: true,
  simple_mode: false,
  match_finished: false,
  current_set: 1,
  serve: '1',
  config: { sets_limit: 5, points_limit: 25 },
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
