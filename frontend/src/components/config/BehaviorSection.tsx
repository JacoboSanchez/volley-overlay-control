import { useI18n } from '../../i18n';

export interface BehaviorSettings {
  autoHide: boolean;
  autoHideSeconds: number;
  autoSimple: boolean;
  autoSimpleOnTimeout: boolean;
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
      <div className="config-switch-row">
        <label className="config-switch-label">
          <input type="checkbox" checked={settings.autoHide}
            onChange={(e) => setSetting('autoHide', e.target.checked)} />
          {t('behavior.autoHide')}
        </label>
      </div>
      {settings.autoHide && (
        <div className="config-range-row">
          <label className="config-label">{t('behavior.hideAfter', { value: settings.autoHideSeconds })}</label>
          <input type="range" min={1} max={15} step={1} value={settings.autoHideSeconds}
            onChange={(e) => setSetting('autoHideSeconds', Number(e.target.value))} className="config-range" />
        </div>
      )}
      <div className="config-switch-row">
        <label className="config-switch-label">
          <input type="checkbox" checked={settings.autoSimple}
            onChange={(e) => setSetting('autoSimple', e.target.checked)} />
          {t('behavior.autoSimple')}
        </label>
      </div>
      {settings.autoSimple && (
        <div className="config-switch-row" style={{ paddingLeft: '1.5rem' }}>
          <label className="config-switch-label">
            <input type="checkbox" checked={settings.autoSimpleOnTimeout}
              onChange={(e) => setSetting('autoSimpleOnTimeout', e.target.checked)} />
            {t('behavior.fullOnTimeout')}
          </label>
        </div>
      )}

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
