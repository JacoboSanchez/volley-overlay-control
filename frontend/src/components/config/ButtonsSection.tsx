import { useI18n } from '../../i18n';
import ColorPicker from '../ColorPicker';
import FontSelector from '../FontSelector';

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
  setSetting: (key: keyof ButtonsSettings, value: ButtonsSettings[keyof ButtonsSettings]) => void;
}

export default function ButtonsSection({ settings, setSetting }: ButtonsSectionProps) {
  const { t } = useI18n();
  return (
    <div className="config-section-buttons">
      <div className="config-switch-row">
        <label className="config-switch-label">
          <input type="checkbox" checked={settings.followTeamColors}
            onChange={(e) => setSetting('followTeamColors', e.target.checked)}
            data-testid="follow-team-colors-switch" />
          {t('buttons.followTeamColors')}
        </label>
      </div>
      {!settings.followTeamColors && (
        <>
          <div className="config-color-grid-2x2">
            <div className="config-color-group">
              <label className="config-label">{t('buttons.t1Btn')}</label>
              <ColorPicker color={settings.team1BtnColor}
                onChange={(c) => setSetting('team1BtnColor', c)}
                data-testid="color-picker-team-1-btn" />
            </div>
            <div className="config-color-group">
              <label className="config-label">{t('buttons.t1Text')}</label>
              <ColorPicker color={settings.team1BtnText}
                onChange={(c) => setSetting('team1BtnText', c)}
                data-testid="color-picker-team-1-text" />
            </div>
            <div className="config-color-group">
              <label className="config-label">{t('buttons.t2Btn')}</label>
              <ColorPicker color={settings.team2BtnColor}
                onChange={(c) => setSetting('team2BtnColor', c)}
                data-testid="color-picker-team-2-btn" />
            </div>
            <div className="config-color-group">
              <label className="config-label">{t('buttons.t2Text')}</label>
              <ColorPicker color={settings.team2BtnText}
                onChange={(c) => setSetting('team2BtnText', c)}
                data-testid="color-picker-team-2-text" />
            </div>
          </div>
          <button className="config-icon-btn" data-testid="reset-colors-button" title={t('buttons.resetColors')}
            onClick={() => {
              setSetting('team1BtnColor', '#2196f3');
              setSetting('team1BtnText', '#ffffff');
              setSetting('team2BtnColor', '#f44336');
              setSetting('team2BtnText', '#ffffff');
            }}>
            <span className="material-icons">replay</span>
          </button>
        </>
      )}
      <div className="config-separator" />
      <div className="config-switch-row">
        <label className="config-switch-label">
          <input type="checkbox" checked={settings.showIcon}
            onChange={(e) => setSetting('showIcon', e.target.checked)}
            data-testid="show-team-icon-switch" />
          {t('buttons.showTeamIcon')}
        </label>
      </div>
      {settings.showIcon && (
        <div className="config-range-row">
          <label className="config-label">{t('buttons.opacity', { value: settings.iconOpacity })}</label>
          <input type="range" min={10} max={100} step={10} value={settings.iconOpacity}
            onChange={(e) => setSetting('iconOpacity', Number(e.target.value))} className="config-range" />
        </div>
      )}
      <div className="config-separator" />
      <div className="config-field-row">
        <label className="config-label">{t('buttons.buttonFont')}</label>
        <FontSelector value={settings.selectedFont}
          onChange={(name) => setSetting('selectedFont', name)} />
      </div>
    </div>
  );
}
