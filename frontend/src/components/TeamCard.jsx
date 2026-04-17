import React, { useState, useCallback } from 'react';
import { useI18n } from '../i18n';
import ColorPicker from './ColorPicker';

/**
 * Team customization card — logo preview, team name selector, colors.
 */
export default function TeamCard({ teamId, model, updateField, predefinedTeams }) {
  const { t } = useI18n();
  const prefix = `Team ${teamId}`;
  const oldNameKey = `${prefix} Text Name`;
  const newNameKey = `${prefix} Name`;
  const nameKey = oldNameKey in model ? oldNameKey : newNameKey;
  const colorKey = `${prefix} Color`;
  const textColorKey = `${prefix} Text Color`;
  const logoKey = `${prefix} Logo`;
  const logoUrl = model[logoKey] ?? '';
  const currentName = model[nameKey] ?? '';
  const [editing, setEditing] = useState(false);

  const teamNames = Object.keys(predefinedTeams);
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
    <div className="config-team-block">
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
          {editing ? (
            <div className="config-combobox-row">
              <input
                type="text"
                className="config-combobox"
                value={currentName}
                onChange={(e) => updateField(nameKey, e.target.value)}
                onBlur={() => setEditing(false)}
                placeholder={t('teams.customPlaceholder')}
                autoFocus
                data-testid={`team-${teamId}-name-selector`}
              />
              <button className="config-combobox-btn"
                onMouseDown={(e) => { e.preventDefault(); setEditing(false); }}
                title={t('teams.backToList')}>
                <span className="material-icons">check</span>
              </button>
            </div>
          ) : (
            <div className="config-combobox-row">
              <select
                className="config-select"
                value={currentName}
                onChange={(e) => handleTeamSelect(e.target.value)}
                data-testid={`team-${teamId}-name-selector`}
              >
                <option value="">{t('teams.select')}</option>
                {allNames.map((name) => (
                  <option key={name} value={name}>{name}</option>
                ))}
              </select>
              <button className="config-combobox-btn" onClick={() => setEditing(true)} title={t('teams.customName')}>
                <span className="material-icons">edit</span>
              </button>
            </div>
          )}
        </div>
      </div>
      <div className="config-color-row">
        <div className="config-color-group">
          <label className="config-label">{t('teams.color')}</label>
          <ColorPicker
            color={model[colorKey] ?? (teamId === 1 ? '#060f8a' : '#ffffff')}
            onChange={(c) => updateField(colorKey, c)}
            data-testid={`team-${teamId}-color-input`}
          />
        </div>
        <div className="config-color-group">
          <label className="config-label">{t('teams.text')}</label>
          <ColorPicker
            color={model[textColorKey] ?? (teamId === 1 ? '#ffffff' : '#000000')}
            onChange={(c) => updateField(textColorKey, c)}
            data-testid={`team-${teamId}-text-color-input`}
          />
        </div>
      </div>
    </div>
  );
}
