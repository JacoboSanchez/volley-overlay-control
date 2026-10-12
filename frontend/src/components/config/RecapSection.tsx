import { useI18n } from '../../i18n';
import type { SetSetting } from '../../hooks/useSettings';
import { ConfigRange, ConfigSwitch, InstantHint } from './fields';
import SetSummaryStylePicker from '../SetSummaryStylePicker';
import type { SetSummaryStyle } from '../../api/board';

export interface RecapSettings {
  setSummaryEnabled: boolean;
  autoShowSetSummary: boolean;
  autoShowSetSummaryDelay: number;
  autoShowSetSummaryDuration: number;
}

export interface RecapSectionProps {
  settings: RecapSettings;
  setSetting: SetSetting;
  /**
   * Set summary overlay — currently selected style (from the broadcast
   * state) and a handler to broadcast a change. When omitted the
   * picker is skipped (e.g. before the session is ready).
   */
  setSummaryStyle?: SetSummaryStyle | undefined;
  onChangeSetSummaryStyle?: ((style: SetSummaryStyle) => void) | undefined;
  overlayStyle?: string | undefined;
  overlayTheme?: string | undefined;
  /**
   * Set summary surface theme ('' matches the scoreboard, 'dark' or
   * 'light'). Independent of the scoreboard theme, so it is available with
   * every overlay style. The selector is skipped without a handler.
   */
  summaryTheme?: string | undefined;
  onChangeSummaryTheme?: ((theme: string) => void) | undefined;
  configuration?: Record<string, unknown> | undefined;
}

export default function RecapSection({
  settings,
  setSetting,
  setSummaryStyle,
  onChangeSetSummaryStyle,
  overlayStyle,
  overlayTheme,
  summaryTheme = '',
  onChangeSummaryTheme,
  configuration,
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
              <SetSummaryStylePicker
                value={setSummaryStyle}
                onChange={onChangeSetSummaryStyle}
                overlayStyle={overlayStyle}
                overlayTheme={overlayTheme}
                summaryTheme={summaryTheme}
                configuration={configuration}
              />
            </div>
          )}
          {onChangeSummaryTheme && (
            <div
              className="config-field-group config-suboption"
              style={{ marginBottom: '0.75rem' }}
            >
              <label className="config-field-group-label">
                {t('config.setSummary.theme.label')}
              </label>
              <select
                className="config-select"
                value={summaryTheme}
                onChange={(e) => onChangeSummaryTheme(e.target.value)}
                data-testid="set-summary-theme-selector"
              >
                <option value="">{t('config.setSummary.theme.matchScoreboard')}</option>
                <option value="dark">{t('overlay.themeDark')}</option>
                <option value="light">{t('overlay.themeLight')}</option>
              </select>
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
