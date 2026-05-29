import { useI18n } from '../../i18n';
import { ConfigSwitch } from './fields';

export interface GeneralSettings {
  haptics: boolean;
  keyboardShortcuts: boolean;
}

export interface GeneralSectionProps {
  settings: GeneralSettings;
  setSetting: <K extends keyof GeneralSettings>(key: K, value: GeneralSettings[K]) => void;
  onShowShortcuts?: () => void;
}

const LANGUAGE_NAMES: Record<string, string> = {
  en: 'English',
  es: 'Español',
  pt: 'Português',
  it: 'Italiano',
  fr: 'Français',
  de: 'Deutsch',
};

export default function GeneralSection({
  settings,
  setSetting,
  onShowShortcuts,
}: GeneralSectionProps) {
  const { t, lang, setLanguage, languages } = useI18n();
  return (
    <div className="config-section-general">
      <ConfigSwitch
        label={t('behavior.haptics')}
        checked={settings.haptics}
        onChange={(v) => setSetting('haptics', v)}
      />
      <ConfigSwitch
        label={t('behavior.keyboardShortcuts')}
        checked={settings.keyboardShortcuts}
        onChange={(v) => setSetting('keyboardShortcuts', v)}
      />
      {settings.keyboardShortcuts && onShowShortcuts && (
        <div className="config-switch-row" style={{ paddingLeft: '1.5rem' }}>
          <button type="button" className="dialog-btn" onClick={onShowShortcuts}>
            {t('behavior.showShortcuts')}
          </button>
        </div>
      )}

      <div className="config-separator" />
      <div className="config-field-row">
        <label className="config-label">{t('lang.label')}</label>
        <select
          className="config-select"
          value={lang}
          onChange={(e) => setLanguage(e.target.value)}
        >
          {languages.map((l) => (
            <option key={l} value={l}>
              {LANGUAGE_NAMES[l] ?? l}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}
