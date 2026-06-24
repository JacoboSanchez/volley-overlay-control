import ColorPicker from '../ColorPicker';
import { useI18n } from '../../i18n';
import type { TeamDraft } from './useTeamDraft';

/** The shared name / logo / colours field set used by every team create form
 *  and inline editor. Stacks one field per row so it reads cleanly in a phone's
 *  portrait column; the two colour pickers sit side by side. */
export default function TeamFieldset({
  draft, idPrefix,
}: {
  draft: TeamDraft;
  idPrefix?: string;
}) {
  const { t } = useI18n();
  const testId = (suffix: string) => (idPrefix ? `${idPrefix}-${suffix}` : undefined);
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
        <input
          className="acc-input"
          value={draft.icon}
          placeholder={t('acc.teams.logoPlaceholder')}
          onChange={(e) => draft.setIcon(e.target.value)}
          data-testid={testId('logo')}
        />
      </label>
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
