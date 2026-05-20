import { useI18n } from '../../i18n';
import FontSelector from '../FontSelector';
import { ConfigColorField, ConfigRange, ConfigSwitch } from './fields';

export interface ButtonsSettings {
  followTeamColors: boolean;
  team1BtnColor: string;
  team1BtnText: string;
  team2BtnColor: string;
  team2BtnText: string;
  showIcon: boolean;
  iconOpacity: number;
  selectedFont: string;
}

export interface ButtonsSectionProps {
  settings: ButtonsSettings;
  setSetting: <K extends keyof ButtonsSettings>(key: K, value: ButtonsSettings[K]) => void;
}

export default function ButtonsSection({ settings, setSetting }: ButtonsSectionProps) {
  const { t } = useI18n();
  return (
    <div className="config-section-buttons">
      <ConfigSwitch
        label={t('buttons.followTeamColors')}
        checked={settings.followTeamColors}
        onChange={(v) => setSetting('followTeamColors', v)}
        testId="follow-team-colors-switch"
      />
      {!settings.followTeamColors && (
        <>
          <div className="config-color-grid-2x2">
            <ConfigColorField
              label={t('buttons.t1Btn')}
              color={settings.team1BtnColor}
              onChange={(c) => setSetting('team1BtnColor', c)}
              testId="color-picker-team-1-btn"
            />
            <ConfigColorField
              label={t('buttons.t1Text')}
              color={settings.team1BtnText}
              onChange={(c) => setSetting('team1BtnText', c)}
              testId="color-picker-team-1-text"
            />
            <ConfigColorField
              label={t('buttons.t2Btn')}
              color={settings.team2BtnColor}
              onChange={(c) => setSetting('team2BtnColor', c)}
              testId="color-picker-team-2-btn"
            />
            <ConfigColorField
              label={t('buttons.t2Text')}
              color={settings.team2BtnText}
              onChange={(c) => setSetting('team2BtnText', c)}
              testId="color-picker-team-2-text"
            />
          </div>
          <button
            className="config-icon-btn"
            data-testid="reset-colors-button"
            title={t('buttons.resetColors')}
            onClick={() => {
              setSetting('team1BtnColor', '#2196f3');
              setSetting('team1BtnText', '#ffffff');
              setSetting('team2BtnColor', '#f44336');
              setSetting('team2BtnText', '#ffffff');
            }}
          >
            <span className="material-icons">replay</span>
          </button>
        </>
      )}
      <div className="config-separator" />
      <ConfigSwitch
        label={t('buttons.showTeamIcon')}
        checked={settings.showIcon}
        onChange={(v) => setSetting('showIcon', v)}
        testId="show-team-icon-switch"
      />
      {settings.showIcon && (
        <ConfigRange
          label={t('buttons.opacity', { value: settings.iconOpacity })}
          value={settings.iconOpacity}
          min={10}
          max={100}
          step={10}
          onChange={(v) => setSetting('iconOpacity', v)}
        />
      )}
      <div className="config-separator" />
      <div className="config-field-row">
        <label className="config-label">{t('buttons.buttonFont')}</label>
        <FontSelector
          value={settings.selectedFont}
          onChange={(name) => setSetting('selectedFont', name)}
        />
      </div>
    </div>
  );
}
