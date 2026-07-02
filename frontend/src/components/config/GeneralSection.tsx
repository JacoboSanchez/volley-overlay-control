import { useI18n } from '../../i18n';
import { ConfigSwitch } from './fields';

export interface GeneralSettings {
  haptics: boolean;
  keyboardShortcuts: boolean;
  showOnAir: boolean;
  showReportLink: boolean;
}

export interface GeneralSectionProps {
  settings: GeneralSettings;
  setSetting: <K extends keyof GeneralSettings>(key: K, value: GeneralSettings[K]) => void;
  onShowShortcuts?: () => void;
}

export default function GeneralSection({
  settings,
  setSetting,
  onShowShortcuts,
}: GeneralSectionProps) {
  const { t } = useI18n();
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
        <div className="config-switch-row config-suboption">
          <button type="button" className="dialog-btn" onClick={onShowShortcuts}>
            {t('behavior.showShortcuts')}
          </button>
        </div>
      )}
      <ConfigSwitch
        label={t('behavior.onAirIndicator')}
        checked={settings.showOnAir}
        onChange={(v) => setSetting('showOnAir', v)}
      />
      <ConfigSwitch
        label={t('behavior.reportLink')}
        checked={settings.showReportLink}
        onChange={(v) => setSetting('showReportLink', v)}
      />
    </div>
  );
}
