import { useI18n } from '../../i18n';
import { ConfigRange, ConfigSwitch } from './fields';
import SetSummaryStylePicker from '../SetSummaryStylePicker';
import type { SetSummaryStyle } from '../../api/client';

export interface BehaviorSettings {
  autoHide: boolean;
  autoHideSeconds: number;
  autoSimple: boolean;
  autoSimpleOnTimeout: boolean;
  haptics: boolean;
  keyboardShortcuts: boolean;
  setSummaryEnabled: boolean;
  autoShowSetSummary: boolean;
  autoShowSetSummaryDelay: number;
  autoShowSetSummaryDuration: number;
}

export interface BehaviorSectionProps {
  settings: BehaviorSettings;
  setSetting: <K extends keyof BehaviorSettings>(key: K, value: BehaviorSettings[K]) => void;
  onShowShortcuts?: () => void;
  /**
   * Set summary overlay — currently selected style (from the broadcast
   * state) and a handler to broadcast a change. When omitted the
   * picker is skipped (e.g. before the session is ready).
   */
  setSummaryStyle?: SetSummaryStyle;
  onChangeSetSummaryStyle?: (style: SetSummaryStyle) => void;
}

const LANGUAGE_NAMES: Record<string, string> = {
  en: 'English',
  es: 'Español',
  pt: 'Português',
  it: 'Italiano',
  fr: 'Français',
  de: 'Deutsch',
};

export default function BehaviorSection({
  settings,
  setSetting,
  onShowShortcuts,
  setSummaryStyle,
  onChangeSetSummaryStyle,
}: BehaviorSectionProps) {
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
            <input
              type="checkbox"
              checked={settings.autoSimpleOnTimeout}
              onChange={(e) => setSetting('autoSimpleOnTimeout', e.target.checked)}
            />
            {t('behavior.fullOnTimeout')}
          </label>
        </div>
      )}
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
              className="config-field-group"
              style={{ paddingLeft: '1.5rem', marginBottom: '0.75rem' }}
            >
              <label className="config-field-group-label">
                {t('config.setSummary.style.label')}
              </label>
              <SetSummaryStylePicker value={setSummaryStyle} onChange={onChangeSetSummaryStyle} />
            </div>
          )}
          <div style={{ paddingLeft: '1.5rem' }}>
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

      <div className="config-separator" />
      <div className="config-field-row">
        <label className="config-label">{t('lang.label')}</label>
        <select
          className="config-select"
          value={lang}
          onChange={(e) => setLanguage(e.target.value)}
        >
          {(languages as string[]).map((l) => (
            <option key={l} value={l}>
              {LANGUAGE_NAMES[l] ?? l}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}
