import React, { useState, useCallback } from 'react';
import * as api from '../api/client';

/**
 * Team customization card — shows logo preview, name, colors, and logo URL.
 * Mirrors the NiceGUI create_team_card layout.
 */
function TeamCard({ teamId, label, model, updateField }) {
  const prefix = `Team ${teamId}`;
  const nameKey = `${prefix} Text Name`;
  const colorKey = `${prefix} Color`;
  const textColorKey = `${prefix} Text Color`;
  const logoKey = `${prefix} Logo`;
  const logoUrl = model[logoKey] ?? '';

  return (
    <div className="config-card">
      <h3 className="config-card-title">{label}</h3>
      <label className="config-label">Name</label>
      <input
        className="config-input"
        value={model[nameKey] ?? ''}
        onChange={(e) => updateField(nameKey, e.target.value)}
        data-testid={`team-${teamId}-name-input`}
      />
      <div className="config-team-row">
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
      <label className="config-label">Logo URL</label>
      <input
        className="config-input"
        value={logoUrl}
        onChange={(e) => updateField(logoKey, e.target.value)}
        placeholder="https://..."
        data-testid={`team-${teamId}-logo-input`}
      />
    </div>
  );
}

/**
 * Configuration panel for team customization, scoreboard options, geometry,
 * and action buttons (save, refresh, reset).
 * Mirrors the NiceGUI CustomizationPage layout.
 */
export default function ConfigPanel({ oid, customization, actions, onBack, onReset }) {
  const [model, setModel] = useState(() => ({ ...customization }));
  const [saving, setSaving] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(!!document.fullscreenElement);

  const updateField = useCallback((key, value) => {
    setModel((m) => ({ ...m, [key]: value }));
  }, []);

  const handleSave = useCallback(async () => {
    setSaving(true);
    try {
      await api.updateCustomization(oid, model);
      onBack();
    } finally {
      setSaving(false);
    }
  }, [oid, model, onBack]);

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

  const toggleFullscreen = useCallback(() => {
    if (document.fullscreenElement) {
      document.exitFullscreen();
      setIsFullscreen(false);
    } else {
      document.documentElement.requestFullscreen().then(() => setIsFullscreen(true));
    }
  }, []);

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
              {model['preferredStyle'] !== undefined && (
                <>
                  <label className="config-label" style={{ marginTop: '0.5rem' }}>Preferred Style</label>
                  <input
                    className="config-input"
                    value={model['preferredStyle'] ?? ''}
                    onChange={(e) => updateField('preferredStyle', e.target.value)}
                    data-testid="style-input"
                  />
                </>
              )}
            </div>
          </div>
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
      </div>
    </div>
  );
}
