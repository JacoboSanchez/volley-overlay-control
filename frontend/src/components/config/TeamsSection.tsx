import TeamCard from '../TeamCard';
import { useI18n } from '../../i18n';
import type { BoardGroup } from '../../api/client';

export type ConfigModel = Record<string, unknown>;

export interface PredefinedTeam {
  icon?: string;
  color?: string;
  text_color?: string;
}

export type PredefinedTeams = Record<string, PredefinedTeam>;

export interface TeamsSectionProps {
  model: ConfigModel;
  updateField: (key: string, value: unknown) => void;
  predefinedTeams: PredefinedTeams;
  /** Selectable team groups for this board (the synthetic "All" group first).
   *  When provided, a group picker narrows the team selectors' options. */
  groups?: BoardGroup[];
  selectedGroupId?: number | null;
  onSelectGroup?: (id: number | null) => void;
}

export default function TeamsSection({
  model,
  updateField,
  predefinedTeams,
  groups,
  selectedGroupId = null,
  onSelectGroup,
}: TeamsSectionProps) {
  const { t } = useI18n();
  return (
    <div className="config-section-teams">
      {groups && groups.length > 0 && onSelectGroup && (
        <div className="config-group-picker">
          <label className="config-label" htmlFor="team-group-picker">
            {t('teams.groupPicker')}
          </label>
          <select
            id="team-group-picker"
            className="config-select"
            value={selectedGroupId ?? ''}
            onChange={(e) => onSelectGroup(e.target.value === '' ? null : Number(e.target.value))}
            data-testid="team-group-picker"
          >
            {groups.map((g) => (
              <option key={g.id ?? 'all'} value={g.id ?? ''}>
                {g.kind === 'all' ? t('teams.allGroup') : g.name} ({g.count})
              </option>
            ))}
          </select>
        </div>
      )}
      <TeamCard
        teamId={1}
        model={model}
        updateField={updateField}
        predefinedTeams={predefinedTeams}
      />
      <div className="config-team-divider" />
      <TeamCard
        teamId={2}
        model={model}
        updateField={updateField}
        predefinedTeams={predefinedTeams}
      />
    </div>
  );
}
