import { useI18n } from '../../i18n';
import type { ConfigModel } from './TeamsSection';
import type { StyleCapabilities } from '../../api/board';
import { asBool, asString } from '../../utils/coerce';
import { ConfigColorField } from './fields';
import VisualStylePicker from '../VisualStylePicker';

export interface OverlaySectionProps {
  model: ConfigModel;
  updateField: (key: string, value: unknown) => void;
  styles: string[];
  /** Per-style capability flags from the backend; drives the theme hint. */
  capabilities?: Record<string, StyleCapabilities>;
}

const THEME_OPTIONS = [
  { value: '', icon: 'brightness_auto', label: 'overlay.themeDefault' },
  { value: 'dark', icon: 'dark_mode', label: 'overlay.themeDark' },
  { value: 'light', icon: 'light_mode', label: 'overlay.themeLight' },
] as const;

export default function OverlaySection({
  model,
  updateField,
  styles,
  capabilities = {},
}: OverlaySectionProps) {
  const { t } = useI18n();
  const hasStyles = Array.isArray(styles) && styles.length > 1;
  // The selected style drives which style-specific knobs are meaningful.
  // An empty preferredStyle falls back to the "default" template.
  const selectedStyle = asString(model['preferredStyle'], '') || 'default';
  // Mirror the overlay runtime: anything but dark/light resolves to default.
  const rawTheme = asString(model['overlayTheme'], '').toLowerCase();
  const overlayTheme = rawTheme === 'dark' || rawTheme === 'light' ? rawTheme : '';
  // The theme always reaches the set summary, so the control is shown for
  // every style; the hint says whether the scoreboard itself follows it.
  const scoreboardIgnoresTheme = capabilities[selectedStyle]?.theme === false;

  return (
    <div className="config-section-overlay">
      <div className="config-switch-row">
        <label className="config-switch-label">
          <input
            type="checkbox"
            checked={asBool(model['Logos'])}
            onChange={(e) => updateField('Logos', e.target.checked ? 'true' : 'false')}
          />
          {t('overlay.logos')}
        </label>
      </div>
      <div className="config-color-grid-2x2">
        <ConfigColorField
          label={t('overlay.setColor')}
          color={asString(model['Color 1'], '#2a2f35')}
          onChange={(c) => updateField('Color 1', c)}
        />
        <ConfigColorField
          label={t('overlay.setText')}
          color={asString(model['Text Color 1'], '#ffffff')}
          onChange={(c) => updateField('Text Color 1', c)}
        />
        <ConfigColorField
          label={t('overlay.gameColor')}
          color={asString(model['Color 2'], '#ffffff')}
          onChange={(c) => updateField('Color 2', c)}
        />
        <ConfigColorField
          label={t('overlay.gameText')}
          color={asString(model['Text Color 2'], '#2a2f35')}
          onChange={(c) => updateField('Text Color 2', c)}
        />
      </div>
      {hasStyles && (
        <div className="config-field-group config-overlay-style">
          <label className="config-field-group-label">{t('overlay.styleLabel')}</label>
          <VisualStylePicker
            kind="overlay"
            value={selectedStyle}
            styles={[...new Set(['default', ...styles])]}
            onChange={(style) => updateField('preferredStyle', style === 'default' ? '' : style)}
            overlayTheme={overlayTheme}
            configuration={model}
            testId="style-selector"
          />
        </div>
      )}
      {/* The vertical placement of edge-pinned styles lives in the Position
          section's anchor grid (paired mode). */}
      <div className="config-field-group config-overlay-theme">
        <label className="config-field-group-label">{t('overlay.themeLabel')}</label>
        <div
          className="config-mode-toggle config-theme-toggle"
          role="radiogroup"
          aria-label={t('overlay.themeLabel')}
          data-testid="overlay-theme-selector"
        >
          {THEME_OPTIONS.map((option) => {
            const active = overlayTheme === option.value;
            return (
              <button
                key={option.value || 'default'}
                type="button"
                role="radio"
                aria-checked={active}
                className={`config-mode-toggle-btn${active ? ' config-mode-toggle-btn-active' : ''}`}
                onClick={() => updateField('overlayTheme', option.value)}
                data-testid={`overlay-theme-${option.value || 'default'}`}
              >
                <span className="material-icons" aria-hidden="true">
                  {option.icon}
                </span>
                {t(option.label)}
              </button>
            );
          })}
        </div>
        <p className="config-hint" data-testid="overlay-theme-hint">
          {t(scoreboardIgnoresTheme ? 'overlay.themeHintSummaryOnly' : 'overlay.themeHint')}
        </p>
      </div>
    </div>
  );
}
