import React, { useState, useCallback, useEffect } from 'react';
import { useI18n } from '../i18n';
import { useSettings } from '../hooks/useSettings';
import { useOrientation } from '../hooks/useOrientation';
import * as api from '../api/client';
import ColorPicker from './ColorPicker';
import TeamCard from './TeamCard';
import FontSelector from './FontSelector';

function copyToClipboard(text) {
  navigator.clipboard.writeText(text).catch(() => {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
  });
}

const SECTIONS = ['teams', 'overlay', 'position', 'buttons', 'behavior', 'links'];
const SECTION_KEYS = {
  teams: 'section.teams',
  overlay: 'section.overlay',
  position: 'section.position',
  buttons: 'section.buttons',
  behavior: 'section.behavior',
  links: 'section.links',
};
const SECTION_ICONS = {
  teams: 'groups',
  overlay: 'palette',
  position: 'open_with',
  buttons: 'touch_app',
  behavior: 'tune',
  links: 'link',
};

export default function ConfigPanel({ oid, customization, actions, onBack, onReset, onLogout, onCustomizationSaved, onCustomizationRefreshed }) {
  const { t, lang, setLanguage, languages } = useI18n();
  const { settings, setSetting } = useSettings();
  const { isPortrait } = useOrientation();

  const [model, setModel] = useState(() => ({ ...customization }));
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);

  useEffect(() => {
    if (customization) {
      setModel({ ...customization });
    }
  }, [customization]);

  const [refreshing, setRefreshing] = useState(false);
  const [predefinedTeams, setPredefinedTeams] = useState({});
  const [themes, setThemes] = useState({});
  const [styles, setStyles] = useState([]);
  const [links, setLinks] = useState(null);
  const [copiedKey, setCopiedKey] = useState(null);
  const [selectedTheme, setSelectedTheme] = useState('');
  const [activeSection, setActiveSection] = useState('teams');

  useEffect(() => {
    api.getTeams().then(setPredefinedTeams).catch(console.warn);
    api.getThemes().then(setThemes).catch(console.warn);
    api.getLinks(oid).then(setLinks).catch(console.warn);
    api.getStyles(oid).then(setStyles).catch(console.warn);
  }, [oid]);

  const updateField = useCallback((key, value) => {
    setModel((m) => ({ ...m, [key]: value }));
  }, []);

  const handleSave = useCallback(async () => {
    setSaving(true);
    setSaveError(null);
    try {
      await api.updateCustomization(oid, model);
      if (onCustomizationSaved) await onCustomizationSaved();
      onBack();
    } catch (e) {
      setSaveError(e.message || t('config.failedToSave'));
    } finally {
      setSaving(false);
    }
  }, [oid, model, onBack, onCustomizationSaved, t]);

  const handleRefresh = useCallback(async () => {
    if (!window.confirm(t('config.reloadConfirm'))) return;
    setRefreshing(true);
    try {
      const fresh = await api.getCustomization(oid);
      setModel({ ...fresh });
      if (onCustomizationRefreshed) onCustomizationRefreshed(fresh);
    } finally {
      setRefreshing(false);
    }
  }, [oid, t, onCustomizationRefreshed]);

  const handleApplyTheme = useCallback((themeName) => {
    const themeData = themes[themeName];
    if (themeData) {
      setModel((m) => ({ ...m, ...themeData }));
    }
  }, [themes]);

  const hasThemes = Object.keys(themes).length > 0;
  const hasStyles = Array.isArray(styles) && styles.length > 1;
  const isCustomOverlay = links?.overlay && !links.overlay.includes('overlays.uno');

  // --- Section renderers ---

  function renderTeamsSection() {
    return (
      <div className="config-section-teams">
        <TeamCard teamId={1} model={model} updateField={updateField} predefinedTeams={predefinedTeams} />
        <div className="config-team-divider" />
        <TeamCard teamId={2} model={model} updateField={updateField} predefinedTeams={predefinedTeams} />
      </div>
    );
  }

  function renderOverlaySection() {
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
                    onClick={() => { if (selectedTheme) handleApplyTheme(selectedTheme); }}
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

  function renderPositionSection() {
    const fields = [
      { labelKey: 'position.height', key: 'Height', def: 10, min: 0, max: 100, step: 0.1 },
      { labelKey: 'position.width', key: 'Width', def: 30, min: 0, max: 100, step: 0.1 },
      { labelKey: 'position.hPos', key: 'Left-Right', def: -33, min: -50, max: 50, step: 0.1 },
      { labelKey: 'position.vPos', key: 'Up-Down', def: -41.1, min: -50, max: 50, step: 0.1 },
    ];
    return (
      <div className="config-section-position">
        <div className="config-stepper-grid">
          {fields.map((f) => {
            const val = model[f.key] ?? f.def;
            return (
              <div key={f.key} className="config-stepper-group">
                <label className="config-label">{t(f.labelKey)}</label>
                <div className="config-stepper">
                  <button className="config-stepper-btn"
                    onClick={() => updateField(f.key, Math.max(f.min, parseFloat((val - f.step).toFixed(1))))}
                    title={t('position.decrease')}>−</button>
                  <input type="number" className="config-stepper-input"
                    value={val} min={f.min} max={f.max} step={f.step}
                    onChange={(e) => updateField(f.key, parseFloat(e.target.value))}
                    data-testid={f.key === 'Height' ? 'height-input' : f.key === 'Width' ? 'width-input' : f.key === 'Left-Right' ? 'hpos-input' : 'vpos-input'}
                  />
                  <button className="config-stepper-btn"
                    onClick={() => updateField(f.key, Math.min(f.max, parseFloat((val + f.step).toFixed(1))))}
                    title={t('position.increase')}>+</button>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  function renderLinksSection() {
    const linkKeys = ['control', 'overlay', 'preview'];
    const availableLinks = linkKeys.filter((key) => links?.[key]);
    return (
      <div className="config-section-links">
        <div className="links-list">
          {availableLinks.length === 0 ? (
            <p className="config-label" style={{ textAlign: 'center', padding: '0.5rem 0' }}>
              {t('links.noLinks')}
            </p>
          ) : availableLinks.map((key) => (
            <div key={key} className="link-row">
              <a href={links[key]} target="_blank" rel="noopener noreferrer" className="link-text">
                {t(`links.${key}`)}
              </a>
              <button className="link-copy-btn" title={t('links.copyToClipboard')}
                onClick={() => {
                  copyToClipboard(links[key]);
                  setCopiedKey(key);
                  setTimeout(() => setCopiedKey(null), 1500);
                }}>
                <span className="material-icons">{copiedKey === key ? 'check' : 'content_copy'}</span>
              </button>
            </div>
          ))}
        </div>
      </div>
    );
  }

  function renderButtonsSection() {
    return (
      <div className="config-section-buttons">
        <div className="config-switch-row">
          <label className="config-switch-label">
            <input type="checkbox" checked={settings.followTeamColors}
              onChange={(e) => setSetting('followTeamColors', e.target.checked)}
              data-testid="follow-team-colors-switch" />
            {t('buttons.followTeamColors')}
          </label>
        </div>
        {!settings.followTeamColors && (
          <>
            <div className="config-color-grid-2x2">
              <div className="config-color-group">
                <label className="config-label">{t('buttons.t1Btn')}</label>
                <ColorPicker color={settings.team1BtnColor}
                  onChange={(c) => setSetting('team1BtnColor', c)}
                  data-testid="color-picker-team-1-btn" />
              </div>
              <div className="config-color-group">
                <label className="config-label">{t('buttons.t1Text')}</label>
                <ColorPicker color={settings.team1BtnText}
                  onChange={(c) => setSetting('team1BtnText', c)}
                  data-testid="color-picker-team-1-text" />
              </div>
              <div className="config-color-group">
                <label className="config-label">{t('buttons.t2Btn')}</label>
                <ColorPicker color={settings.team2BtnColor}
                  onChange={(c) => setSetting('team2BtnColor', c)}
                  data-testid="color-picker-team-2-btn" />
              </div>
              <div className="config-color-group">
                <label className="config-label">{t('buttons.t2Text')}</label>
                <ColorPicker color={settings.team2BtnText}
                  onChange={(c) => setSetting('team2BtnText', c)}
                  data-testid="color-picker-team-2-text" />
              </div>
            </div>
            <button className="config-icon-btn" data-testid="reset-colors-button" title={t('buttons.resetColors')}
              onClick={() => {
                setSetting('team1BtnColor', '#2196f3');
                setSetting('team1BtnText', '#ffffff');
                setSetting('team2BtnColor', '#f44336');
                setSetting('team2BtnText', '#ffffff');
              }}>
              <span className="material-icons">replay</span>
            </button>
          </>
        )}
        <div className="config-separator" />
        <div className="config-switch-row">
          <label className="config-switch-label">
            <input type="checkbox" checked={settings.showIcon}
              onChange={(e) => setSetting('showIcon', e.target.checked)}
              data-testid="show-team-icon-switch" />
            {t('buttons.showTeamIcon')}
          </label>
        </div>
        {settings.showIcon && (
          <div className="config-range-row">
            <label className="config-label">{t('buttons.opacity', { value: settings.iconOpacity })}</label>
            <input type="range" min={10} max={100} step={10} value={settings.iconOpacity}
              onChange={(e) => setSetting('iconOpacity', Number(e.target.value))} className="config-range" />
          </div>
        )}
        <div className="config-separator" />
        <div className="config-field-row">
          <label className="config-label">{t('buttons.buttonFont')}</label>
          <FontSelector value={settings.selectedFont}
            onChange={(name) => setSetting('selectedFont', name)} />
        </div>
      </div>
    );
  }

  function renderBehaviorSection() {
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
            {languages.map((l) => (
              <option key={l} value={l}>{l === 'en' ? 'English' : l === 'es' ? 'Español' : l}</option>
            ))}
          </select>
        </div>
      </div>
    );
  }

  function renderSection(sec) {
    switch (sec) {
      case 'teams': return renderTeamsSection();
      case 'overlay': return renderOverlaySection();
      case 'position': return renderPositionSection();
      case 'buttons': return renderButtonsSection();
      case 'behavior': return renderBehaviorSection();
      case 'links': return renderLinksSection();
      default: return null;
    }
  }

  return (
    <div className="config-panel">
      {/* Sticky top bar */}
      <div className="config-top-bar">
        <button className="config-top-btn" onClick={onBack} title={t('config.backToScoreboard')}
          data-testid="scoreboard-tab-button">
          <span className="material-icons">arrow_back</span>
        </button>
        <span className="config-top-title">{t('config.title')}</span>
        <div style={{ minWidth: 44 }} />
      </div>

      {/* Main body */}
      <div className={`config-body ${isPortrait ? 'config-body-portrait' : 'config-body-landscape'}`}>
        {isPortrait ? (
          <div className="config-accordion">
            {SECTIONS.map((sec) => (
              <div key={sec} className="config-accordion-item">
                <button
                  className={`config-accordion-header ${activeSection === sec ? 'config-accordion-header-active' : ''}`}
                  onClick={() => setActiveSection(activeSection === sec ? null : sec)}
                >
                  <span className="material-icons">{SECTION_ICONS[sec]}</span>
                  {t(SECTION_KEYS[sec])}
                  <span className="material-icons config-accordion-chevron">
                    {activeSection === sec ? 'expand_less' : 'expand_more'}
                  </span>
                </button>
                {activeSection === sec && (
                  <div className="config-accordion-body">
                    {renderSection(sec)}
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : (
          <>
            <nav className="config-sidebar">
              {SECTIONS.map((sec) => (
                <button
                  key={sec}
                  className={`config-sidebar-item ${activeSection === sec ? 'config-sidebar-item-active' : ''}`}
                  onClick={() => setActiveSection(sec)}
                >
                  <span className="material-icons">{SECTION_ICONS[sec]}</span>
                  <span className="config-sidebar-label">{t(SECTION_KEYS[sec])}</span>
                </button>
              ))}
            </nav>
            <div className="config-section-content">
              {renderSection(activeSection)}
            </div>
          </>
        )}
      </div>

      {/* Fixed bottom bar */}
      <div className="config-bottom-bar">
        <button className="config-bottom-btn config-bottom-btn-save"
          onClick={handleSave} disabled={saving} title={t('config.saveCustomization')} data-testid="save-button">
          <span className="material-icons">save</span>
          <span>{saving ? '...' : t('config.save')}</span>
        </button>
        <div className="spacer" />
        <button className="config-bottom-btn config-bottom-btn-refresh" onClick={handleRefresh}
          disabled={refreshing} title={t('config.reloadFromServer')} data-testid="refresh-button">
          <span className="material-icons">sync</span>
        </button>
        <button className="config-bottom-btn config-bottom-btn-reset" onClick={onReset}
          title={t('config.resetMatch')} data-testid="reset-button">
          <span className="material-icons">recycling</span>
        </button>
        <button className="config-bottom-btn config-bottom-btn-logout"
          onClick={() => { if (window.confirm(t('config.logoutConfirm'))) onLogout(); }}
          title={t('config.logout')} data-testid="logout-button">
          <span className="material-icons">logout</span>
        </button>
      </div>

      {/* Save error */}
      {saveError && (
        <div className="config-save-error">{saveError}</div>
      )}

    </div>
  );
}
