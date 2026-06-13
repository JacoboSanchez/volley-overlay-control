import { useI18n } from '../../i18n';
import type { ConfigModel } from './TeamsSection';
import type { StyleCapabilities } from '../../api/client';
import { asBool, asString } from '../../utils/coerce';
import { ConfigColorField } from './fields';

export interface OverlaySectionProps {
  model: ConfigModel;
  updateField: (key: string, value: unknown) => void;
  styles: string[];
  /** Per-style capability flags from the backend; gates the theme + anchor knobs. */
  capabilities?: Record<string, StyleCapabilities>;
  isCustomOverlay: boolean;
}

export default function OverlaySection({
  model,
  updateField,
  styles,
  capabilities = {},
  isCustomOverlay,
}: OverlaySectionProps) {
  const { t } = useI18n();
  const hasStyles = Array.isArray(styles) && styles.length > 1;
  // The selected style drives which style-specific knobs are meaningful.
  // An empty preferredStyle falls back to the "default" template.
  const selectedStyle = asString(model['preferredStyle'], '') || 'default';
  const caps = capabilities[selectedStyle];
  const showTheme = !!caps?.theme;
  const showAnchor = !!caps?.verticalAnchor;

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
        {!isCustomOverlay && (
          <label className="config-switch-label">
            <input
              type="checkbox"
              checked={asBool(model['Gradient'])}
              onChange={(e) => updateField('Gradient', e.target.checked ? 'true' : 'false')}
            />
            {t('overlay.gradient')}
          </label>
        )}
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
        <div className="config-theme-inline">
          <div className="config-field-group">
            <label className="config-field-group-label">{t('overlay.styleLabel')}</label>
            <select
              className="config-select"
              value={asString(model['preferredStyle'], '')}
              onChange={(e) => updateField('preferredStyle', e.target.value)}
              data-testid="style-selector"
            >
              <option value="">{t('overlay.style')}</option>
              {styles.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </div>
          {/* Theme + vertical-anchor only appear for styles where they
              have a visible effect (reported by the backend). */}
          {showTheme && (
            <div className="config-field-group">
              <label className="config-field-group-label">{t('overlay.themeLabel')}</label>
              <select
                className="config-select"
                value={asString(model['overlayTheme'], '')}
                onChange={(e) => updateField('overlayTheme', e.target.value)}
                data-testid="overlay-theme-selector"
              >
                <option value="">{t('overlay.themeDefault')}</option>
                <option value="dark">{t('overlay.themeDark')}</option>
                <option value="light">{t('overlay.themeLight')}</option>
              </select>
            </div>
          )}
          {showAnchor && (
            <div className="config-field-group">
              <label className="config-field-group-label">
                {t('overlay.verticalAnchorLabel')}
              </label>
              <select
                className="config-select"
                value={asString(model['verticalAnchor'], '')}
                onChange={(e) => updateField('verticalAnchor', e.target.value)}
                data-testid="vertical-anchor-selector"
              >
                <option value="">{t('overlay.anchorCenter')}</option>
                <option value="top">{t('overlay.anchorTop')}</option>
                <option value="bottom">{t('overlay.anchorBottom')}</option>
              </select>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
