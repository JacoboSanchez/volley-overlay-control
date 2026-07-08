import { useState } from 'react';
import ColorPicker from '../ColorPicker';
import IconPickerDialog from '../icons/IconPickerDialog';
import { useI18n } from '../../i18n';
import type { TeamDraft } from './useTeamDraft';

/** The shared name / logo / colours field set used by every team create form
 *  and inline editor. Stacks one field per row so it reads cleanly in a phone's
 *  portrait column; the two colour pickers sit side by side. The logo field
 *  takes a pasted URL or a pick from the hosted icon library. */
export default function TeamFieldset({
  draft,
  idPrefix,
  iconPickerScope = 'personal',
}: {
  draft: TeamDraft;
  idPrefix?: string;
  /** Where the picker's inline upload lands: personal library everywhere,
   *  the global library on the admin catalog pages. */
  iconPickerScope?: 'personal' | 'global';
}) {
  const { t } = useI18n();
  const [pickerOpen, setPickerOpen] = useState(false);
  const testId = (suffix: string) => (idPrefix ? `${idPrefix}-${suffix}` : undefined);
  // Soft hint only — the field legitimately holds /media/… library paths and
  // the server validates on save; this just catches obvious paste mistakes
  // (and http:// values that would trip mixed-content on an HTTPS deploy).
  const icon = draft.icon.trim();
  const oddLogoUrl = icon !== '' && !/^(https:\/\/|\/)/i.test(icon);
  return (
    <div className="acc-tfields">
      <label className="acc-field acc-tfield">
        <span>{t('acc.teams.fieldName')}</span>
        <input
          className="acc-input"
          value={draft.name}
          onChange={(e) => draft.setName(e.target.value)}
          data-testid={testId('name')}
        />
      </label>
      <label className="acc-field acc-tfield">
        <span>{t('acc.teams.fieldLogoShort')}</span>
        <div className="acc-tfield-logo">
          <input
            className="acc-input"
            value={draft.icon}
            placeholder={t('acc.teams.logoPlaceholder')}
            onChange={(e) => draft.setIcon(e.target.value)}
            data-testid={testId('logo')}
          />
          <button
            type="button"
            className="acc-btn secondary"
            onClick={() => setPickerOpen(true)}
            data-testid={testId('logo-browse')}
          >
            {t('acc.teams.browseLibrary')}
          </button>
        </div>
        {oddLogoUrl && (
          <span className="acc-muted" data-testid={testId('logo-hint')}>
            {t('acc.teams.logoUrlHint')}
          </span>
        )}
      </label>
      <IconPickerDialog
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        onSelect={(url) => draft.setIcon(url)}
        uploadScope={iconPickerScope}
      />
      <div className="acc-tfields__colors">
        <div className="acc-field acc-tfield acc-tfield-color">
          <span>{t('acc.teams.fieldColour')}</span>
          <ColorPicker
            color={draft.color}
            onChange={draft.setColor}
            aria-label={t('acc.teams.fieldColour')}
            data-testid={testId('color')}
          />
        </div>
        <div className="acc-field acc-tfield acc-tfield-color">
          <span>{t('acc.teams.fieldText')}</span>
          <ColorPicker
            color={draft.textColor}
            onChange={draft.setTextColor}
            aria-label={t('acc.teams.fieldText')}
            data-testid={testId('text-color')}
          />
        </div>
      </div>
    </div>
  );
}
