import type { Translate } from '../i18n';
import { asBool, asColor, asString } from '../utils/coerce';

export interface StylePreviewTeam {
  name: string;
  short_name: string;
  color_primary: string;
  color_secondary: string;
  logo_url: string;
}

/** Appearance only: examples keep their own scores and never receive credentials. */
export interface StylePreviewAppearance {
  team_home: StylePreviewTeam;
  team_away: StylePreviewTeam;
  show_logos: boolean;
  colors: { set_bg: string; set_text: string; game_bg: string; game_text: string };
  verticalAnchor: string;
}

export function stylePreviewAppearance(
  model: Record<string, unknown>,
  t: Translate,
): StylePreviewAppearance {
  const team = (id: 1 | 2): StylePreviewTeam => {
    const prefix = `Team ${id}`;
    const oldKey = `${prefix} Text Name`;
    const name = asString(
      model[oldKey in model ? oldKey : `${prefix} Name`],
      t(`stylePicker.team${id}`),
    );
    return {
      name,
      short_name: name.slice(0, 3).toUpperCase(),
      color_primary: asColor(model[`${prefix} Color`], id === 1 ? '#060f8a' : '#ffffff'),
      color_secondary: asColor(model[`${prefix} Text Color`], id === 1 ? '#ffffff' : '#000000'),
      logo_url: asString(model[`${prefix} Logo`], ''),
    };
  };
  return {
    team_home: team(1),
    team_away: team(2),
    show_logos: asBool(model['Logos'], true),
    colors: {
      set_bg: asColor(model['Color 1'], '#2a2f35'),
      set_text: asColor(model['Text Color 1'], '#ffffff'),
      game_bg: asColor(model['Color 2'], '#ffffff'),
      game_text: asColor(model['Text Color 2'], '#2a2f35'),
    },
    verticalAnchor: asString(model['verticalAnchor'], 'top'),
  };
}
