import { useMemo } from 'react';
import type { ScoreButtonFontStyle } from '../components/ScoreButton';
import type { Settings } from './useSettings';
import { TEAM_A_COLOR, TEAM_B_COLOR, FONT_SCALES, DEFAULT_FONT_SCALE } from '../theme';
import { asColor, asString } from '../utils/coerce';

type Customization = Record<string, unknown>;

interface FontScale {
  scale: number;
  offset_y: number;
  offset_x: number;
}

export interface UseButtonThemeResult {
  btnColorA: string;
  btnTextA: string;
  btnColorB: string;
  btnTextB: string;
  iconLogoA: string | null;
  iconLogoB: string | null;
  fontStyle: ScoreButtonFontStyle;
}

/**
 * Score-button colours, logos and font style derived from the
 * operator settings and the overlay customization.
 */
export function useButtonTheme({
  settings,
  customization,
}: {
  settings: Settings;
  customization: Customization | null;
}): UseButtonThemeResult {
  // Memoize the four button colours together so the strings keep
  // referential identity across re-renders that didn't change any
  // colour input. Without this, every WebSocket state push would
  // hand fresh string instances to TeamPanel/CenterPanel and defeat
  // the React.memo wrappers that guard those subtrees.
  const { btnColorA, btnTextA, btnColorB, btnTextB } = useMemo(
    () => ({
      btnColorA: settings.followTeamColors
        ? asColor(customization?.['Team 1 Color'], TEAM_A_COLOR)
        : (settings.team1BtnColor ?? TEAM_A_COLOR),
      btnTextA: settings.followTeamColors
        ? asColor(customization?.['Team 1 Text Color'], '#ffffff')
        : (settings.team1BtnText ?? '#ffffff'),
      btnColorB: settings.followTeamColors
        ? asColor(customization?.['Team 2 Color'], TEAM_B_COLOR)
        : (settings.team2BtnColor ?? TEAM_B_COLOR),
      btnTextB: settings.followTeamColors
        ? asColor(customization?.['Team 2 Text Color'], '#ffffff')
        : (settings.team2BtnText ?? '#ffffff'),
    }),
    [
      settings.followTeamColors,
      settings.team1BtnColor,
      settings.team1BtnText,
      settings.team2BtnColor,
      settings.team2BtnText,
      customization,
    ],
  );

  const iconLogoA = settings.showIcon ? asString(customization?.['Team 1 Logo']) : null;
  const iconLogoB = settings.showIcon ? asString(customization?.['Team 2 Logo']) : null;

  const fontStyle = useMemo<ScoreButtonFontStyle>(() => {
    const fontProps: FontScale = FONT_SCALES[settings.selectedFont] ?? DEFAULT_FONT_SCALE;
    return settings.selectedFont && settings.selectedFont !== 'Default'
      ? {
          fontFamily: `'${settings.selectedFont}'`,
          fontScale: fontProps.scale,
          fontOffsetY: fontProps.offset_y,
          fontOffsetX: fontProps.offset_x,
        }
      : { fontFamily: undefined, fontScale: 1.0, fontOffsetY: 0.0, fontOffsetX: 0.0 };
  }, [settings.selectedFont]);

  return { btnColorA, btnTextA, btnColorB, btnTextB, iconLogoA, iconLogoB, fontStyle };
}
