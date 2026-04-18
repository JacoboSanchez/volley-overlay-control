import TeamCard from '../TeamCard';

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
}

export default function TeamsSection({ model, updateField, predefinedTeams }: TeamsSectionProps) {
  return (
    <div className="config-section-teams">
      <TeamCard teamId={1} model={model} updateField={updateField} predefinedTeams={predefinedTeams} />
      <div className="config-team-divider" />
      <TeamCard teamId={2} model={model} updateField={updateField} predefinedTeams={predefinedTeams} />
    </div>
  );
}
