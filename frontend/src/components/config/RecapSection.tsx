import { useI18n } from '../../i18n';
import { ConfigRange, ConfigSwitch, InstantHint } from './fields';
import SetSummaryStylePicker from '../SetSummaryStylePicker';
import type { SetSummaryStyle } from '../../api/client';

export interface RecapSettings {
  setSummaryEnabled: boolean;
  autoShowSetSummary: boolean;
  autoShowSetSummaryDelay: number;
  autoShowSetSummaryDuration: number;
}

export interface RecapSectionProps {
  settings: RecapSettings;
  setSetting: <K extends keyof RecapSettings>(key: K, value: RecapSettings[K]) => void;
  /**
   * Set summary overlay — currently selected style (from the broadcast
   * state) and a handler to broadcast a change. When omitted the
   * picker is skipped (e.g. before the session is ready).
   */
  setSummaryStyle?: SetSummaryStyle;
  onChangeSetSummaryStyle?: (style: SetSummaryStyle) => void;
}

export default function RecapSection({
  settings,
  setSetting,
  setSummaryStyle,
  onChangeSetSummaryStyle,
}: RecapSectionProps) {
  const { t } = useI18n();
  return (
    <div className="config-section-recap">
      <InstantHint />
      <ConfigSwitch
        label={t('config.setSummary.label')}
        checked={settings.setSummaryEnabled}
        onChange={(v) => setSetting('setSummaryEnabled', v)}
      />
      {settings.setSummaryEnabled && (
        <>
          <p
            className="config-help-text"
            style={{ margin: '0 0 0.75rem 1.5rem', fontSize: '0.85em', opacity: 0.7 }}
          >
            {t('config.setSummary.description')}
          </p>
          {setSummaryStyle && onChangeSetSummaryStyle && (
            <div
              className="config-field-group config-suboption"
              style={{ marginBottom: '0.75rem' }}
            >
              <label className="config-field-group-label">
                {t('config.setSummary.style.label')}
              </label>
              <SetSummaryStylePicker value={setSummaryStyle} onChange={onChangeSetSummaryStyle} />
            </div>
          )}
          <div className="config-suboption">
            <ConfigSwitch
              label={t('behavior.autoShowSetSummary')}
              checked={settings.autoShowSetSummary}
              onChange={(v) => setSetting('autoShowSetSummary', v)}
            />
            {settings.autoShowSetSummary && (
              <>
                <ConfigRange
                  label={t('behavior.autoShowSetSummary.delay', {
                    value: settings.autoShowSetSummaryDelay,
                  })}
                  value={settings.autoShowSetSummaryDelay}
                  min={0}
                  max={30}
                  step={1}
                  onChange={(v) => setSetting('autoShowSetSummaryDelay', v)}
                />
                <ConfigRange
                  label={t('behavior.autoShowSetSummary.duration', {
                    value: settings.autoShowSetSummaryDuration,
                  })}
                  value={settings.autoShowSetSummaryDuration}
                  min={5}
                  max={60}
                  step={1}
                  onChange={(v) => setSetting('autoShowSetSummaryDuration', v)}
                />
              </>
            )}
          </div>
        </>
      )}
    </div>
  );
}
