import { lazy } from 'react';
import type { MatchMode } from '../../api/board';
import type { SetSummaryStyle } from '../../api/board';
import type { Settings, SetSetting } from '../../hooks/useSettings';
import { asString } from '../../utils/coerce';
import type { ConfigModel } from '../TeamCard';
import type { SectionId } from './sections';
import type { ConfigOptions } from './useConfigOptions';

const TeamsSection = lazy(() => import('./TeamsSection'));
const OverlaySection = lazy(() => import('./OverlaySection'));
const PositionSection = lazy(() => import('./PositionSection'));
const ButtonsSection = lazy(() => import('./ButtonsSection'));
const DisplaySection = lazy(() => import('./DisplaySection'));
const StatsSection = lazy(() => import('./StatsSection'));
const RecapSection = lazy(() => import('./RecapSection'));
const GeneralSection = lazy(() => import('./GeneralSection'));
const LinksSection = lazy(() => import('./LinksSection'));
const MatchRulesSection = lazy(() => import('./MatchRulesSection'));
const PresetPicker = lazy(() => import('../PresetPicker'));

export interface ConfigSectionBodyProps {
  section: SectionId | null;
  oid: string;
  model: ConfigModel;
  updateField: (key: string, value: unknown) => void;
  onApplyPatch: (patch: ConfigModel) => void;
  options: ConfigOptions;
  settings: Settings;
  setSetting: SetSetting;
  /** Live ``state.config`` from useGameState; ``null`` while connecting. */
  gameConfig?: Record<string, unknown> | null | undefined;
  autoSwapSides?: boolean | null | undefined;
  onShowShortcuts?: (() => void) | undefined;
  setSummaryStyle?: SetSummaryStyle | undefined;
  onChangeSetSummaryStyle?: ((style: SetSummaryStyle) => void) | undefined;
}

/** Renders the one section the panel is showing. Every section is a lazy
 *  chunk, so the panel only downloads what the operator actually opens. */
export default function ConfigSectionBody({
  section,
  oid,
  model,
  updateField,
  onApplyPatch,
  options,
  settings,
  setSetting,
  gameConfig,
  autoSwapSides = null,
  onShowShortcuts,
  setSummaryStyle,
  onChangeSetSummaryStyle,
}: ConfigSectionBodyProps) {
  switch (section) {
    case 'presets':
      return <PresetPicker model={model} onApplyPatch={onApplyPatch} />;
    case 'teams':
      return (
        <TeamsSection
          model={model}
          updateField={updateField}
          predefinedTeams={options.predefinedTeams}
          groups={options.groups}
          selectedGroupId={options.selectedGroupId}
          onSelectGroup={options.selectGroup}
        />
      );
    case 'overlay':
      return (
        <OverlaySection
          model={model}
          updateField={updateField}
          styles={options.styles}
          capabilities={options.styleCaps}
        />
      );
    case 'position': {
      // Edge-pinned styles (pylons/corners) ignore the free x/y geometry;
      // the anchor grid switches to the paired top/center/bottom mode.
      const selectedStyle = asString(model['preferredStyle'], '') || 'default';
      const edgePinned = !!options.styleCaps[selectedStyle]?.verticalAnchor;
      return <PositionSection model={model} updateField={updateField} edgePinned={edgePinned} />;
    }
    case 'buttons':
      return <ButtonsSection settings={settings} setSetting={setSetting} />;
    case 'display':
      return <DisplaySection settings={settings} setSetting={setSetting} />;
    case 'stats':
      return <StatsSection settings={settings} setSetting={setSetting} />;
    case 'recap':
      return (
        <RecapSection
          settings={settings}
          setSetting={setSetting}
          setSummaryStyle={setSummaryStyle}
          onChangeSetSummaryStyle={onChangeSetSummaryStyle}
        />
      );
    case 'general':
      return (
        <GeneralSection
          settings={settings}
          setSetting={setSetting}
          onShowShortcuts={onShowShortcuts}
        />
      );
    case 'rules':
      return (
        <MatchRulesSection
          oid={oid}
          autoSwapSides={autoSwapSides}
          mode={(gameConfig?.mode as MatchMode | undefined) ?? null}
          pointsLimit={(gameConfig?.points_limit as number | undefined) ?? null}
          pointsLimitLastSet={(gameConfig?.points_limit_last_set as number | undefined) ?? null}
          setsLimit={(gameConfig?.sets_limit as number | undefined) ?? null}
        />
      );
    case 'links':
      return <LinksSection links={options.links} />;
    default:
      return null;
  }
}
