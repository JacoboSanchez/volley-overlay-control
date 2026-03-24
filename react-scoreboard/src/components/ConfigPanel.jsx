import React, { useState, useCallback } from 'react';
import * as api from '../api/client';

/**
 * Configuration panel for team customization, save, refresh, and reset.
 * Mirrors the NiceGUI CustomizationPage layout.
 */
export default function ConfigPanel({ oid, customization, actions, onBack, onReset }) {
  const [model, setModel] = useState(() => ({ ...customization }));
  const [saving, setSaving] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

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

  return (
    <div className="config-panel">
      <div className="config-scroll">
        {/* Team 1 card */}
        <div className="config-card">
          <h3 className="config-card-title">Team 1 (Home)</h3>
          <label className="config-label">Name</label>
          <input
            className="config-input"
            value={model['Team 1 Text Name'] ?? ''}
            onChange={(e) => updateField('Team 1 Text Name', e.target.value)}
            data-testid="team-1-name-input"
          />
          <div className="config-color-row">
            <div className="config-color-group">
              <label className="config-label">Color</label>
              <input
                type="color"
                className="config-color-input"
                value={model['Team 1 Color'] ?? '#060f8a'}
                onChange={(e) => updateField('Team 1 Color', e.target.value)}
                data-testid="team-1-color-input"
              />
            </div>
            <div className="config-color-group">
              <label className="config-label">Text</label>
              <input
                type="color"
                className="config-color-input"
                value={model['Team 1 Text Color'] ?? '#ffffff'}
                onChange={(e) => updateField('Team 1 Text Color', e.target.value)}
                data-testid="team-1-text-color-input"
              />
            </div>
          </div>
          <label className="config-label">Logo URL</label>
          <input
            className="config-input"
            value={model['Team 1 Logo'] ?? ''}
            onChange={(e) => updateField('Team 1 Logo', e.target.value)}
            placeholder="https://..."
            data-testid="team-1-logo-input"
          />
        </div>

        {/* Team 2 card */}
        <div className="config-card">
          <h3 className="config-card-title">Team 2 (Away)</h3>
          <label className="config-label">Name</label>
          <input
            className="config-input"
            value={model['Team 2 Text Name'] ?? ''}
            onChange={(e) => updateField('Team 2 Text Name', e.target.value)}
            data-testid="team-2-name-input"
          />
          <div className="config-color-row">
            <div className="config-color-group">
              <label className="config-label">Color</label>
              <input
                type="color"
                className="config-color-input"
                value={model['Team 2 Color'] ?? '#ffffff'}
                onChange={(e) => updateField('Team 2 Color', e.target.value)}
                data-testid="team-2-color-input"
              />
            </div>
            <div className="config-color-group">
              <label className="config-label">Text</label>
              <input
                type="color"
                className="config-color-input"
                value={model['Team 2 Text Color'] ?? '#000000'}
                onChange={(e) => updateField('Team 2 Text Color', e.target.value)}
                data-testid="team-2-text-color-input"
              />
            </div>
          </div>
          <label className="config-label">Logo URL</label>
          <input
            className="config-input"
            value={model['Team 2 Logo'] ?? ''}
            onChange={(e) => updateField('Team 2 Logo', e.target.value)}
            placeholder="https://..."
            data-testid="team-2-logo-input"
          />
        </div>

        {/* Scoreboard options card */}
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

        {/* Geometry card */}
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
        </div>
      </div>

      {/* Action buttons */}
      <div className="control-buttons">
        <button
          className="control-btn control-btn-config"
          onClick={onBack}
          title="Back to scoreboard"
          data-testid="scoreboard-tab-button"
        >
          <span className="material-icons">keyboard_arrow_left</span>
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
