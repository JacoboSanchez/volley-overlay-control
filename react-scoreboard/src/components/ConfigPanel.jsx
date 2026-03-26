import React, { useState, useCallback, useEffect } from 'react';
import * as api from '../api/client';
import { FONT_OPTIONS } from '../theme';

/**
 * Team customization card — logo preview, team name selector, colors.
 * Mirrors the NiceGUI create_team_card layout.
 */
function TeamCard({ teamId, label, model, updateField, predefinedTeams }) {
  const prefix = `Team ${teamId}`;
  // Backend uses either old key "Team N Text Name" or new key "Team N Name"
  const oldNameKey = `${prefix} Text Name`;
  const newNameKey = `${prefix} Name`;
  const nameKey = oldNameKey in model ? oldNameKey : newNameKey;
  const colorKey = `${prefix} Color`;
  const textColorKey = `${prefix} Text Color`;
  const logoKey = `${prefix} Logo`;
  const logoUrl = model[logoKey] ?? '';
  const currentName = model[nameKey] ?? '';

  const teamNames = Object.keys(predefinedTeams);
  // Add current name if not in the predefined list
  const allNames = teamNames.includes(currentName) || !currentName
    ? teamNames
    : [...teamNames, currentName];

  const handleTeamSelect = useCallback((name) => {
    updateField(nameKey, name);
    const team = predefinedTeams[name];
    if (team) {
      if (team.icon) updateField(logoKey, team.icon);
      if (team.color) updateField(colorKey, team.color);
      if (team.text_color) updateField(textColorKey, team.text_color);
    }
  }, [predefinedTeams, updateField, nameKey, logoKey, colorKey, textColorKey]);

  return (
    <div className="config-card">
      <div className="config-team-header">
        <div className="config-logo-preview" data-testid={`team-${teamId}-logo-preview`}>
          {logoUrl ? (
            <img
              src={logoUrl}
              alt={`Team ${teamId} logo`}
              className="config-logo-img"
              onError={(e) => { e.target.style.display = 'none'; }}
            />
          ) : (
            <span className="material-icons config-logo-placeholder">image</span>
          )}
        </div>
        <div className="config-team-header-fields">
          <label className="config-label">Name</label>
          <select
            className="config-select"
            value={currentName}
            onChange={(e) => handleTeamSelect(e.target.value)}
            data-testid={`team-${teamId}-name-selector`}
          >
            <option value="">— Select —</option>
            {allNames.map((name) => (
              <option key={name} value={name}>{name}</option>
            ))}
          </select>
        </div>
      </div>
      <div className="config-color-row">
        <div className="config-color-group">
          <label className="config-label">Color</label>
          <input
            type="color"
            className="config-color-input"
            value={model[colorKey] ?? (teamId === 1 ? '#060f8a' : '#ffffff')}
            onChange={(e) => updateField(colorKey, e.target.value)}
            data-testid={`team-${teamId}-color-input`}
          />
        </div>
        <div className="config-color-group">
          <label className="config-label">Text</label>
          <input
            type="color"
            className="config-color-input"
            value={model[textColorKey] ?? (teamId === 1 ? '#ffffff' : '#000000')}
            onChange={(e) => updateField(textColorKey, e.target.value)}
            data-testid={`team-${teamId}-text-color-input`}
          />
        </div>
      </div>
    </div>
  );
}

/**
 * Links dialog — control, overlay, and preview links with copy buttons.
 */
function LinksDialog({ links, onClose }) {
  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text).catch(() => {
      // Fallback: select from a temporary textarea
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
    });
  };

  return (
    <div className="dialog-overlay" onClick={onClose}>
      <div className="dialog-card" onClick={(e) => e.stopPropagation()}>
        <h3 className="dialog-title">Links</h3>
        <div className="links-list">
          {links.control && (
            <div className="link-row">
              <a href={links.control} target="_blank" rel="noopener noreferrer" className="link-text">
                Control
              </a>
              <button
                className="link-copy-btn"
                onClick={() => copyToClipboard(links.control)}
                title="Copy to clipboard"
              >
                <span className="material-icons">content_copy</span>
              </button>
            </div>
          )}
          {links.overlay && (
            <div className="link-row">
              <a href={links.overlay} target="_blank" rel="noopener noreferrer" className="link-text">
                Overlay
              </a>
              <button
                className="link-copy-btn"
                onClick={() => copyToClipboard(links.overlay)}
                title="Copy to clipboard"
              >
                <span className="material-icons">content_copy</span>
              </button>
            </div>
          )}
          {links.preview && (
            <div className="link-row">
              <a href={links.preview} target="_blank" rel="noopener noreferrer" className="link-text">
                Preview
              </a>
              <button
                className="link-copy-btn"
                onClick={() => copyToClipboard(links.preview)}
                title="Copy to clipboard"
              >
                <span className="material-icons">content_copy</span>
              </button>
            </div>
          )}
          {!links.control && !links.overlay && !links.preview && (
            <p className="config-label" style={{ textAlign: 'center', padding: '0.5rem 0' }}>
              No links available for this session.
            </p>
          )}
        </div>
        <div className="dialog-actions">
          <button className="dialog-btn dialog-btn-cancel" onClick={onClose}>
            <span className="material-icons">close</span>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

/**
 * Theme dialog — select and apply a predefined theme.
 */
function ThemeDialog({ themes, onApply, onClose }) {
  const [selected, setSelected] = useState('');
  const themeNames = Object.keys(themes);

  if (themeNames.length === 0) {
    return (
      <div className="dialog-overlay" onClick={onClose}>
        <div className="dialog-card" onClick={(e) => e.stopPropagation()}>
          <h3 className="dialog-title">Themes</h3>
          <p className="config-label" style={{ textAlign: 'center', padding: '0.5rem 0' }}>
            No themes available.
          </p>
          <div className="dialog-actions">
            <button className="dialog-btn dialog-btn-cancel" onClick={onClose}>
              <span className="material-icons">close</span>
              Close
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="dialog-overlay" onClick={onClose}>
      <div className="dialog-card" onClick={(e) => e.stopPropagation()}>
        <h3 className="dialog-title">Themes</h3>
        <select
          className="config-select"
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
          data-testid="theme-selector"
        >
          <option value="">— Select a theme —</option>
          {themeNames.map((name) => (
            <option key={name} value={name}>{name}</option>
          ))}
        </select>
        <div className="dialog-actions" style={{ marginTop: '1rem' }}>
          <button
            className="dialog-btn dialog-btn-ok"
            onClick={() => { if (selected) { onApply(selected); onClose(); } }}
            disabled={!selected}
          >
            <span className="material-icons">done</span>
            Load
          </button>
          <button className="dialog-btn dialog-btn-cancel" onClick={onClose}>
            <span className="material-icons">close</span>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

/**
 * Configuration panel for team customization, scoreboard options, geometry,
 * links, themes, and action buttons (save, refresh, reset).
 * Mirrors the NiceGUI CustomizationPage layout.
 */
const LS_PREFIX = 'volley_';
function loadLocal(key, fallback) {
  try {
    const v = localStorage.getItem(LS_PREFIX + key);
    return v !== null ? JSON.parse(v) : fallback;
  } catch { return fallback; }
}
function saveLocal(key, value) {
  localStorage.setItem(LS_PREFIX + key, JSON.stringify(value));
}

/**
 * Options card — auto-hide, button colors, show icon, opacity.
 * Mirrors the NiceGUI OptionsDialog.
 */
function OptionsCard({ settings, onSettingsChange }) {
  const update = (key, value) => {
    const next = { ...settings, [key]: value };
    onSettingsChange(next);
    saveLocal(key, value);
  };

  return (
    <div className="config-card">
      <h3 className="config-card-title">Options</h3>

      {/* Auto-hide */}
      <div className="config-switch-row">
        <label className="config-switch-label">
          <input
            type="checkbox"
            checked={settings.autoHide}
            onChange={(e) => update('autoHide', e.target.checked)}
          />
          Auto-hide scoreboard
        </label>
      </div>
      {settings.autoHide && (
        <div className="config-range-row">
          <label className="config-label">Hide after {settings.autoHideSeconds}s</label>
          <input
            type="range"
            min={1}
            max={15}
            step={1}
            value={settings.autoHideSeconds}
            onChange={(e) => update('autoHideSeconds', Number(e.target.value))}
            className="config-range"
          />
        </div>
      )}

      {/* Auto simple mode */}
      <div className="config-switch-row">
        <label className="config-switch-label">
          <input
            type="checkbox"
            checked={settings.autoSimple}
            onChange={(e) => update('autoSimple', e.target.checked)}
          />
          Auto simple mode
        </label>
      </div>
      {settings.autoSimple && (
        <div className="config-switch-row" style={{ paddingLeft: '1.5rem' }}>
          <label className="config-switch-label">
            <input
              type="checkbox"
              checked={settings.autoSimpleOnTimeout}
              onChange={(e) => update('autoSimpleOnTimeout', e.target.checked)}
            />
            Full mode on timeout
          </label>
        </div>
      )}

      <div className="config-separator" />

      {/* Button configuration */}
      <h3 className="config-card-subtitle">Button Colors</h3>
      <div className="config-switch-row">
        <label className="config-switch-label">
          <input
            type="checkbox"
            checked={settings.followTeamColors}
            onChange={(e) => update('followTeamColors', e.target.checked)}
            data-testid="follow-team-colors-switch"
          />
          Follow team colors
        </label>
      </div>
      {!settings.followTeamColors && (
        <div className="config-color-row">
          <div className="config-color-group">
            <label className="config-label">T1 Btn</label>
            <input
              type="color"
              className="config-color-input"
              value={settings.team1BtnColor}
              onChange={(e) => update('team1BtnColor', e.target.value)}
              data-testid="color-picker-team-1-btn"
            />
          </div>
          <div className="config-color-group">
            <label className="config-label">T1 Text</label>
            <input
              type="color"
              className="config-color-input"
              value={settings.team1BtnText}
              onChange={(e) => update('team1BtnText', e.target.value)}
              data-testid="color-picker-team-1-text"
            />
          </div>
          <div className="config-color-group">
            <label className="config-label">T2 Btn</label>
            <input
              type="color"
              className="config-color-input"
              value={settings.team2BtnColor}
              onChange={(e) => update('team2BtnColor', e.target.value)}
              data-testid="color-picker-team-2-btn"
            />
          </div>
          <div className="config-color-group">
            <label className="config-label">T2 Text</label>
            <input
              type="color"
              className="config-color-input"
              value={settings.team2BtnText}
              onChange={(e) => update('team2BtnText', e.target.value)}
              data-testid="color-picker-team-2-text"
            />
          </div>
          <button
            className="config-icon-btn"
            onClick={() => {
              update('team1BtnColor', '#2196f3');
              update('team1BtnText', '#ffffff');
              update('team2BtnColor', '#f44336');
              update('team2BtnText', '#ffffff');
            }}
            title="Reset colors"
            data-testid="reset-colors-button"
          >
            <span className="material-icons">replay</span>
          </button>
        </div>
      )}

      <div className="config-separator" />

      {/* Show icon */}
      <div className="config-switch-row">
        <label className="config-switch-label">
          <input
            type="checkbox"
            checked={settings.showIcon}
            onChange={(e) => update('showIcon', e.target.checked)}
            data-testid="show-team-icon-switch"
          />
          Show team icon on buttons
        </label>
      </div>
      {settings.showIcon && (
        <div className="config-range-row">
          <label className="config-label">Icon opacity: {settings.iconOpacity}%</label>
          <input
            type="range"
            min={10}
            max={100}
            step={10}
            value={settings.iconOpacity}
            onChange={(e) => update('iconOpacity', Number(e.target.value))}
            className="config-range"
          />
        </div>
      )}

      <div className="config-separator" />

      {/* Button font */}
      <div className="config-field-row">
        <label className="config-label">Button font</label>
        <select
          className="config-select"
          value={settings.selectedFont}
          onChange={(e) => update('selectedFont', e.target.value)}
          style={{ fontFamily: settings.selectedFont !== 'Default' ? `'${settings.selectedFont}'` : undefined }}
          data-testid="font-selector"
        >
          {FONT_OPTIONS.map((name) => (
            <option
              key={name}
              value={name}
              style={{ fontFamily: name !== 'Default' ? `'${name}'` : undefined }}
            >
              {name}
            </option>
          ))}
        </select>
      </div>

      <div className="config-separator" />

      {/* Show preview */}
      <div className="config-switch-row">
        <label className="config-switch-label">
          <input
            type="checkbox"
            checked={settings.showPreview}
            onChange={(e) => update('showPreview', e.target.checked)}
            data-testid="show-preview-switch"
          />
          Show overlay preview
        </label>
      </div>
    </div>
  );
}

export default function ConfigPanel({ oid, customization, actions, onBack, onReset, onLogout, onCustomizationSaved }) {
  const [model, setModel] = useState(() => ({ ...customization }));
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);

  // Sync model when customization prop updates (e.g. after external refresh)
  useEffect(() => {
    if (customization) {
      setModel({ ...customization });
    }
  }, [customization]);
  const [refreshing, setRefreshing] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(!!document.fullscreenElement);
  const [predefinedTeams, setPredefinedTeams] = useState({});
  const [themes, setThemes] = useState({});
  const [links, setLinks] = useState(null);
  const [showLinks, setShowLinks] = useState(false);
  const [showThemes, setShowThemes] = useState(false);
  const [localSettings, setLocalSettings] = useState(() => ({
    autoHide: loadLocal('autoHide', false),
    autoHideSeconds: loadLocal('autoHideSeconds', 5),
    autoSimple: loadLocal('autoSimple', false),
    autoSimpleOnTimeout: loadLocal('autoSimpleOnTimeout', false),
    followTeamColors: loadLocal('followTeamColors', true),
    team1BtnColor: loadLocal('team1BtnColor', '#2196f3'),
    team1BtnText: loadLocal('team1BtnText', '#ffffff'),
    team2BtnColor: loadLocal('team2BtnColor', '#f44336'),
    team2BtnText: loadLocal('team2BtnText', '#ffffff'),
    showIcon: loadLocal('showIcon', false),
    iconOpacity: loadLocal('iconOpacity', 50),
    showPreview: loadLocal('showPreview', false),
    selectedFont: loadLocal('selectedFont', 'Default'),
  }));

  // Fetch predefined data on mount
  useEffect(() => {
    api.getTeams().then(setPredefinedTeams).catch(() => {});
    api.getThemes().then(setThemes).catch(() => {});
    api.getLinks(oid).then(setLinks).catch(() => {});
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
      setSaveError(e.message || 'Failed to save customization');
    } finally {
      setSaving(false);
    }
  }, [oid, model, onBack, onCustomizationSaved]);

  const handleRefresh = useCallback(async () => {
    if (!window.confirm('Reload customization from server?')) return;
    setRefreshing(true);
    try {
      const fresh = await api.getCustomization(oid);
      setModel({ ...fresh });
    } finally {
      setRefreshing(false);
    }
  }, [oid]);

  const handleApplyTheme = useCallback((themeName) => {
    const themeData = themes[themeName];
    if (themeData) {
      setModel((m) => ({ ...m, ...themeData }));
    }
  }, [themes]);

  const toggleFullscreen = useCallback(() => {
    if (document.fullscreenElement) {
      document.exitFullscreen();
      setIsFullscreen(false);
    } else {
      document.documentElement.requestFullscreen().then(() => setIsFullscreen(true));
    }
  }, []);

  const hasThemes = Object.keys(themes).length > 0;

  return (
    <div className="config-panel">
      <div className="config-scroll">
        <div className="config-columns">
          {/* Left column: Team 1 + Scoreboard Options */}
          <div className="config-column">
            <TeamCard
              teamId={1}
              label="Team 1 (Home)"
              model={model}
              updateField={updateField}
              predefinedTeams={predefinedTeams}
            />
            <div className="config-card">
              <h3 className="config-card-title">Scoreboard Options</h3>
              <div className="config-switch-row">
                <label className="config-switch-label">
                  <input
                    type="checkbox"
                    checked={model['Logos'] === 'true' || model['Logos'] === true}
                    onChange={(e) => updateField('Logos', e.target.checked ? 'true' : 'false')}
                  />
                  Show Logos
                </label>
                <label className="config-switch-label">
                  <input
                    type="checkbox"
                    checked={model['Gradient'] === 'true' || model['Gradient'] === true}
                    onChange={(e) => updateField('Gradient', e.target.checked ? 'true' : 'false')}
                  />
                  Gradient
                </label>
              </div>
              <div className="config-color-row">
                <div className="config-color-group">
                  <label className="config-label">Set Color</label>
                  <input
                    type="color"
                    className="config-color-input"
                    value={model['Color 1'] ?? '#2a2f35'}
                    onChange={(e) => updateField('Color 1', e.target.value)}
                  />
                </div>
                <div className="config-color-group">
                  <label className="config-label">Set Text</label>
                  <input
                    type="color"
                    className="config-color-input"
                    value={model['Text Color 1'] ?? '#ffffff'}
                    onChange={(e) => updateField('Text Color 1', e.target.value)}
                  />
                </div>
                <div className="config-color-group">
                  <label className="config-label">Game Color</label>
                  <input
                    type="color"
                    className="config-color-input"
                    value={model['Color 2'] ?? '#ffffff'}
                    onChange={(e) => updateField('Color 2', e.target.value)}
                  />
                </div>
                <div className="config-color-group">
                  <label className="config-label">Game Text</label>
                  <input
                    type="color"
                    className="config-color-input"
                    value={model['Text Color 2'] ?? '#2a2f35'}
                    onChange={(e) => updateField('Text Color 2', e.target.value)}
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Right column: Team 2 + Geometry */}
          <div className="config-column">
            <TeamCard
              teamId={2}
              label="Team 2 (Away)"
              model={model}
              updateField={updateField}
              predefinedTeams={predefinedTeams}
            />
            <div className="config-card">
              <h3 className="config-card-title">Position &amp; Size</h3>
              <div className="config-number-row">
                <div className="config-number-group">
                  <label className="config-label">Height</label>
                  <input
                    type="number"
                    className="config-number-input"
                    value={model['Height'] ?? 10}
                    min={0}
                    max={100}
                    step={0.1}
                    onChange={(e) => updateField('Height', parseFloat(e.target.value))}
                    data-testid="height-input"
                  />
                </div>
                <div className="config-number-group">
                  <label className="config-label">Width</label>
                  <input
                    type="number"
                    className="config-number-input"
                    value={model['Width'] ?? 30}
                    min={0}
                    max={100}
                    step={0.1}
                    onChange={(e) => updateField('Width', parseFloat(e.target.value))}
                    data-testid="width-input"
                  />
                </div>
                <div className="config-number-group">
                  <label className="config-label">H Pos</label>
                  <input
                    type="number"
                    className="config-number-input"
                    value={model['Left-Right'] ?? -33}
                    min={-50}
                    max={50}
                    step={0.1}
                    onChange={(e) => updateField('Left-Right', parseFloat(e.target.value))}
                    data-testid="hpos-input"
                  />
                </div>
                <div className="config-number-group">
                  <label className="config-label">V Pos</label>
                  <input
                    type="number"
                    className="config-number-input"
                    value={model['Up-Down'] ?? -41.1}
                    min={-50}
                    max={50}
                    step={0.1}
                    onChange={(e) => updateField('Up-Down', parseFloat(e.target.value))}
                    data-testid="vpos-input"
                  />
                </div>
              </div>
              {/* Utility row: theme + links */}
              <div className="config-utility-row">
                {hasThemes && (
                  <button
                    className="config-icon-btn"
                    onClick={() => setShowThemes(true)}
                    title="Themes"
                    data-testid="theme-button"
                  >
                    <span className="material-icons">palette</span>
                  </button>
                )}
                <button
                  className="config-icon-btn config-icon-btn-primary"
                  onClick={() => setShowLinks(true)}
                  title="Links"
                  data-testid="links-button"
                >
                  <span className="material-icons">link</span>
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Options card — spans full width below the two columns */}
        <div className="config-options-row">
          <OptionsCard
            settings={localSettings}
            onSettingsChange={setLocalSettings}
          />
        </div>
      </div>

      {/* Action buttons — mirrors NiceGUI _create_action_buttons */}
      <div className="control-buttons">
        <button
          className="control-btn control-btn-config"
          onClick={onBack}
          title="Back to scoreboard"
          data-testid="scoreboard-tab-button"
        >
          <span className="material-icons">keyboard_arrow_left</span>
        </button>

        <button
          className="control-btn control-btn-fullscreen"
          onClick={toggleFullscreen}
          title={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}
          data-testid="fullscreen-button"
        >
          <span className="material-icons">
            {isFullscreen ? 'fullscreen_exit' : 'fullscreen'}
          </span>
        </button>

        <div className="spacer" />

        <button
          className="control-btn control-btn-save"
          onClick={handleSave}
          title="Save customization"
          disabled={saving}
          data-testid="save-button"
        >
          <span className="material-icons">save</span>
        </button>
        <button
          className="control-btn control-btn-refresh"
          onClick={handleRefresh}
          title="Reload from server"
          disabled={refreshing}
          data-testid="refresh-button"
        >
          <span className="material-icons">sync</span>
        </button>
        <button
          className="control-btn control-btn-reset"
          onClick={onReset}
          title="Reset match"
          data-testid="reset-button"
        >
          <span className="material-icons">recycling</span>
        </button>
        <button
          className="control-btn control-btn-logout"
          onClick={() => { if (window.confirm('Disconnect and return to OID entry?')) onLogout(); }}
          title="Logout"
          data-testid="logout-button"
        >
          <span className="material-icons">logout</span>
        </button>
      </div>

      {/* Save error message */}
      {saveError && (
        <p className="init-error" style={{ textAlign: 'center', margin: '0.5rem 1rem' }}>{saveError}</p>
      )}

      {/* Dialogs */}
      {showLinks && links && (
        <LinksDialog links={links} onClose={() => setShowLinks(false)} />
      )}
      {showThemes && (
        <ThemeDialog themes={themes} onApply={handleApplyTheme} onClose={() => setShowThemes(false)} />
      )}
    </div>
  );
}
