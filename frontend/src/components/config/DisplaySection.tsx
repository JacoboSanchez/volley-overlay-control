import { useI18n } from '../../i18n';
import { ConfigRange, ConfigSwitch } from './fields';

export interface DisplaySettings {
  autoHide: boolean;
  autoHideSeconds: number;
  autoSimple: boolean;
  autoSimpleOnTimeout: boolean;
}

export interface DisplaySectionProps {
  settings: DisplaySettings;
  setSetting: <K extends keyof DisplaySettings>(key: K, value: DisplaySettings[K]) => void;
}

export default function DisplaySection({ settings, setSetting }: DisplaySectionProps) {
  const { t } = useI18n();
  return (
    <div className="config-section-display">
      <ConfigSwitch
        label={t('behavior.autoHide')}
        checked={settings.autoHide}
        onChange={(v) => setSetting('autoHide', v)}
      />
      {settings.autoHide && (
        <ConfigRange
          label={t('behavior.hideAfter', { value: settings.autoHideSeconds })}
          value={settings.autoHideSeconds}
          min={1}
          max={15}
          step={1}
          onChange={(v) => setSetting('autoHideSeconds', v)}
        />
      )}
      <ConfigSwitch
        label={t('behavior.autoSimple')}
        checked={settings.autoSimple}
        onChange={(v) => setSetting('autoSimple', v)}
      />
      {settings.autoSimple && (
        <div className="config-switch-row" style={{ paddingLeft: '1.5rem' }}>
          <label className="config-switch-label">
            <input
              type="checkbox"
              checked={settings.autoSimpleOnTimeout}
              onChange={(e) => setSetting('autoSimpleOnTimeout', e.target.checked)}
            />
            {t('behavior.fullOnTimeout')}
          </label>
        </div>
      )}
    </div>
  );
}
