import React from 'react';
import { useI18n } from '../../i18n';
import ColorPicker from '../ColorPicker';

export default function OverlaySection({
  model,
  updateField,
  themes,
  styles,
  selectedTheme,
  setSelectedTheme,
  onApplyTheme,
  isCustomOverlay,
}) {
  const { t } = useI18n();
  const hasThemes = Object.keys(themes).length > 0;
  const hasStyles = Array.isArray(styles) && styles.length > 1;

  return (
    <div className="config-section-overlay">
      <div className="config-switch-row">
        <label className="config-switch-label">
          <input
            type="checkbox"
            checked={model['Logos'] === 'true' || model['Logos'] === true}
            onChange={(e) => updateField('Logos', e.target.checked ? 'true' : 'false')}
          />
          {t('overlay.logos')}
        </label>
        {!isCustomOverlay && (
          <label className="config-switch-label">
            <input
              type="checkbox"
              checked={model['Gradient'] === 'true' || model['Gradient'] === true}
              onChange={(e) => updateField('Gradient', e.target.checked ? 'true' : 'false')}
            />
            {t('overlay.gradient')}
          </label>
        )}
      </div>
      <div className="config-color-grid-2x2">
        <div className="config-color-group">
          <label className="config-label">{t('overlay.setColor')}</label>
          <ColorPicker color={model['Color 1'] ?? '#2a2f35'}
            onChange={(c) => updateField('Color 1', c)} />
        </div>
        <div className="config-color-group">
          <label className="config-label">{t('overlay.setText')}</label>
          <ColorPicker color={model['Text Color 1'] ?? '#ffffff'}
            onChange={(c) => updateField('Text Color 1', c)} />
        </div>
        <div className="config-color-group">
          <label className="config-label">{t('overlay.gameColor')}</label>
          <ColorPicker color={model['Color 2'] ?? '#ffffff'}
            onChange={(c) => updateField('Color 2', c)} />
        </div>
        <div className="config-color-group">
          <label className="config-label">{t('overlay.gameText')}</label>
          <ColorPicker color={model['Text Color 2'] ?? '#2a2f35'}
            onChange={(c) => updateField('Text Color 2', c)} />
        </div>
      </div>
      {(hasStyles || hasThemes) && (
        <div className="config-theme-inline">
          {hasStyles && (
            <div className="config-field-group">
              <label className="config-field-group-label">{t('overlay.styleLabel')}</label>
              <select className="config-select" value={model['preferredStyle'] ?? ''}
                onChange={(e) => updateField('preferredStyle', e.target.value)}
                data-testid="style-selector">
                <option value="">{t('overlay.style')}</option>
                {styles.map((name) => (
                  <option key={name} value={name}>{name}</option>
                ))}
              </select>
            </div>
          )}
          {hasThemes && (
            <div className="config-field-group">
              <label className="config-field-group-label">{t('overlay.preloadedConfigLabel')}</label>
              <div className="config-field-group-row">
                <select className="config-select" value={selectedTheme}
                  onChange={(e) => setSelectedTheme(e.target.value)} data-testid="theme-selector">
                  <option value="">{t('overlay.selectAndLoad')}</option>
                  {Object.keys(themes).map((name) => (
                    <option key={name} value={name}>{name}</option>
                  ))}
                </select>
                <button className="config-inline-btn" data-testid="theme-button"
                  onClick={() => { if (selectedTheme) onApplyTheme(selectedTheme); }}
                  disabled={!selectedTheme}>
                  <span className="material-icons">download</span>
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
