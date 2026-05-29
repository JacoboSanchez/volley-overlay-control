import { useI18n } from '../../i18n';
import { ConfigSwitch } from './fields';

export interface StatsSettings {
  trackPointTypes: boolean;
  extendedErrorTracking: boolean;
}

export interface StatsSectionProps {
  settings: StatsSettings;
  setSetting: <K extends keyof StatsSettings>(key: K, value: StatsSettings[K]) => void;
}

export default function StatsSection({ settings, setSetting }: StatsSectionProps) {
  const { t } = useI18n();
  return (
    <div className="config-section-stats">
      <ConfigSwitch
        label={t('behavior.trackPointTypes')}
        checked={settings.trackPointTypes}
        onChange={(v) => setSetting('trackPointTypes', v)}
      />
      {settings.trackPointTypes && (
        <div style={{ paddingLeft: '1.5rem' }}>
          <p
            className="config-help-text"
            style={{ margin: '0 0 0.5rem', fontSize: '0.85em', opacity: 0.7 }}
          >
            {t('behavior.trackPointTypes.description')}
          </p>
          <ConfigSwitch
            label={t('behavior.extendedErrorTracking')}
            checked={settings.extendedErrorTracking}
            onChange={(v) => setSetting('extendedErrorTracking', v)}
          />
        </div>
      )}
    </div>
  );
}
