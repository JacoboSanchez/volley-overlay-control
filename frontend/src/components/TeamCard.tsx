import { useEffect, useState, useCallback } from 'react';
import { useI18n } from '../i18n';
import ColorPicker from './ColorPicker';
import Dialog from './Dialog';
import { asString } from '../utils/coerce';

export type ConfigModel = Record<string, unknown>;

export interface PredefinedTeam {
  icon?: string;
  color?: string;
  text_color?: string;
}

export type PredefinedTeams = Record<string, PredefinedTeam>;

export interface TeamCardProps {
  teamId: 1 | 2;
  model: ConfigModel;
  updateField: (key: string, value: unknown) => void;
  predefinedTeams: PredefinedTeams;
}

/**
 * Team customization card — logo preview, team name selector, colors.
 */
export default function TeamCard({ teamId, model, updateField, predefinedTeams }: TeamCardProps) {
  const { t } = useI18n();
  const prefix = `Team ${teamId}`;
  const oldNameKey = `${prefix} Text Name`;
  const newNameKey = `${prefix} Name`;
  const nameKey = oldNameKey in model ? oldNameKey : newNameKey;
  const colorKey = `${prefix} Color`;
  const textColorKey = `${prefix} Text Color`;
  const logoKey = `${prefix} Logo`;
  const logoUrl = asString(model[logoKey], '');
  const currentName = asString(model[nameKey], '');
  const [editing, setEditing] = useState(false);
  // The logo URL editor is a rarely-needed control — it lives behind the
  // logo preview (click to open) instead of adding a row to every card.
  const [logoDialogOpen, setLogoDialogOpen] = useState(false);
  // A broken logo URL must stay visible as a problem (placeholder + hint),
  // not silently vanish. Reset whenever the URL changes.
  const [logoError, setLogoError] = useState(false);
  useEffect(() => {
    setLogoError(false);
  }, [logoUrl]);

  const teamNames = Object.keys(predefinedTeams);
  const allNames =
    teamNames.includes(currentName) || !currentName ? teamNames : [...teamNames, currentName];

  const handleTeamSelect = useCallback(
    (name: string) => {
      updateField(nameKey, name);
      const team = predefinedTeams[name];
      if (team) {
        if (team.icon) updateField(logoKey, team.icon);
        if (team.color) updateField(colorKey, team.color);
        if (team.text_color) updateField(textColorKey, team.text_color);
      }
    },
    [predefinedTeams, updateField, nameKey, logoKey, colorKey, textColorKey],
  );

  return (
    <div className="config-team-block">
      <div className="config-team-header">
        <button
          type="button"
          className="config-logo-preview config-logo-preview-btn"
          data-testid={`team-${teamId}-logo-preview`}
          onClick={() => setLogoDialogOpen(true)}
          title={t('teams.editLogo')}
          aria-label={`${t('teams.editLogo')} — ${currentName || prefix}`}
        >
          {logoUrl && !logoError ? (
            <img
              src={logoUrl}
              alt={`Team ${teamId} logo`}
              className="config-logo-img"
              onError={() => setLogoError(true)}
            />
          ) : (
            <span className="material-icons config-logo-placeholder">
              {logoError ? 'broken_image' : 'image'}
            </span>
          )}
          <span className="material-icons config-logo-edit-badge" aria-hidden="true">
            edit
          </span>
        </button>
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
                // eslint-disable-next-line jsx-a11y/no-autofocus -- focus the inline editor the moment edit mode opens
                autoFocus
                data-testid={`team-${teamId}-name-selector`}
              />
              <button
                className="config-combobox-btn"
                onMouseDown={(e) => {
                  e.preventDefault();
                  setEditing(false);
                }}
                title={t('teams.backToList')}
                aria-label={t('teams.backToList')}
              >
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
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
              <button
                className="config-combobox-btn"
                onClick={() => setEditing(true)}
                title={t('teams.customName')}
                aria-label={t('teams.customName')}
              >
                <span className="material-icons">edit</span>
              </button>
            </div>
          )}
        </div>
      </div>
      <Dialog
        open={logoDialogOpen}
        onClose={() => setLogoDialogOpen(false)}
        ariaLabelledBy={`team-${teamId}-logo-dialog-title`}
      >
        <h3 className="dialog-title" id={`team-${teamId}-logo-dialog-title`}>
          {t('teams.editLogo')} — {currentName || prefix}
        </h3>
        <label className="config-label" htmlFor={`team-${teamId}-logo-url`}>
          {t('teams.logoUrl')}
        </label>
        <div className="config-combobox-row">
          <input
            id={`team-${teamId}-logo-url`}
            type="url"
            className="config-combobox"
            value={logoUrl}
            onChange={(e) => updateField(logoKey, e.target.value.trim())}
            placeholder="https://…"
            data-testid={`team-${teamId}-logo-url`}
          />
          <button
            className="config-combobox-btn"
            onClick={() => updateField(logoKey, '')}
            disabled={!logoUrl}
            title={t('teams.logoClear')}
            aria-label={t('teams.logoClear')}
            data-testid={`team-${teamId}-logo-clear`}
          >
            <span className="material-icons">close</span>
          </button>
        </div>
        {logoError && (
          <p className="config-hint config-field-error" role="alert">
            {t('teams.logoError')}
          </p>
        )}
        <div className="dialog-actions">
          <button
            type="button"
            className="dialog-btn dialog-btn-ok"
            onClick={() => setLogoDialogOpen(false)}
            data-testid={`team-${teamId}-logo-done`}
          >
            {t('dialog.ok')}
          </button>
        </div>
      </Dialog>
      <div className="config-color-row">
        <div className="config-color-group">
          <label className="config-label">{t('teams.color')}</label>
          <ColorPicker
            color={asString(model[colorKey], teamId === 1 ? '#060f8a' : '#ffffff')}
            onChange={(c) => updateField(colorKey, c)}
            data-testid={`team-${teamId}-color-input`}
            aria-label={`${t('teams.color')} — ${currentName || prefix}`}
          />
        </div>
        <div className="config-color-group">
          <label className="config-label">{t('teams.text')}</label>
          <ColorPicker
            color={asString(model[textColorKey], teamId === 1 ? '#ffffff' : '#000000')}
            onChange={(c) => updateField(textColorKey, c)}
            data-testid={`team-${teamId}-text-color-input`}
            aria-label={`${t('teams.text')} — ${currentName || prefix}`}
          />
        </div>
      </div>
    </div>
  );
}
