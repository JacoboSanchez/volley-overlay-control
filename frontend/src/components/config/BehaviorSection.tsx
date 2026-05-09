import { useI18n } from '../../i18n';
import { ConfigRange, ConfigSwitch } from './fields';

export interface BehaviorSettings {
  autoHide: boolean;
  autoHideSeconds: number;
  autoSimple: boolean;
  autoSimpleOnTimeout: boolean;
  haptics: boolean;
}

export interface BehaviorSectionProps {
  settings: BehaviorSettings;
  setSetting: <K extends keyof BehaviorSettings>(key: K, value: BehaviorSettings[K]) => void;
}

const LANGUAGE_NAMES: Record<string, string> = {
  en: 'English',
  es: 'Español',
  pt: 'Português',
  it: 'Italiano',
  fr: 'Français',
  de: 'Deutsch',
};

export default function BehaviorSection({ settings, setSetting }: BehaviorSectionProps) {
  const { t, lang, setLanguage, languages } = useI18n();
  return (
    <div className="config-section-behavior">
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
            <input type="checkbox" checked={settings.autoSimpleOnTimeout}
              onChange={(e) => setSetting('autoSimpleOnTimeout', e.target.checked)} />
            {t('behavior.fullOnTimeout')}
          </label>
        </div>
      )}
      <ConfigSwitch
        label={t('behavior.haptics')}
        checked={settings.haptics}
        onChange={(v) => setSetting('haptics', v)}
      />

      <div className="config-separator" />
      <div className="config-field-row">
        <label className="config-label">{t('lang.label')}</label>
        <select className="config-select" value={lang} onChange={(e) => setLanguage(e.target.value)}>
          {(languages as string[]).map((l) => (
            <option key={l} value={l}>{LANGUAGE_NAMES[l] ?? l}</option>
          ))}
        </select>
      </div>
    </div>
  );
}
