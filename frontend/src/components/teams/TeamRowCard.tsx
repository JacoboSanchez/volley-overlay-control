import { ReactNode } from 'react';
import type { TeamOut } from '../../api/client';
import { useI18n } from '../../i18n';
import { SwatchBox } from './TeamSwatch';

/** One team rendered as a tap-friendly card. The always-visible row carries an
 *  optional select checkbox, the swatch + name, an optional pill (e.g.
 *  "custom"), and an optional Edit toggle; the expandable editor (passed as
 *  `children`) drops below the row full-width when `editing` is true. */
export default function TeamRowCard({
  team, selected, onToggleSelect, pill, editable, editing, onToggleEdit, children,
}: {
  team: TeamOut;
  selected?: boolean;
  onToggleSelect?: () => void;
  pill?: ReactNode;
  editable?: boolean;
  editing?: boolean;
  onToggleEdit?: () => void;
  children?: ReactNode;
}) {
  const { t } = useI18n();
  return (
    <div className={`acc-tcard${selected ? ' is-selected' : ''}`}>
      <div className="acc-tcard__main">
        {onToggleSelect && (
          <label className="acc-tcard__check">
            <input
              type="checkbox"
              checked={!!selected}
              aria-label={t('acc.teams.selectTeam', { name: team.name })}
              onChange={onToggleSelect}
            />
          </label>
        )}
        <SwatchBox color={team.color} textColor={team.text_color} icon={team.icon} name={team.name} />
        <span className="acc-tcard__name">{team.name}</span>
        {pill}
        <span className="acc-tcard__spacer" />
        {editable && onToggleEdit && (
          <button
            className={`acc-btn ghost acc-tcard__edit${editing ? ' is-active' : ''}`}
            aria-expanded={!!editing}
            onClick={onToggleEdit}
          >
            {editing ? t('acc.common.close') : t('acc.common.edit')}
          </button>
        )}
      </div>
      {editing && children && <div className="acc-tcard__editor">{children}</div>}
    </div>
  );
}
