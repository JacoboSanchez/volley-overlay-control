import React from 'react';
import TeamCard from '../TeamCard';

export default function TeamsSection({ model, updateField, predefinedTeams }) {
  return (
    <div className="config-section-teams">
      <TeamCard teamId={1} model={model} updateField={updateField} predefinedTeams={predefinedTeams} />
      <div className="config-team-divider" />
      <TeamCard teamId={2} model={model} updateField={updateField} predefinedTeams={predefinedTeams} />
    </div>
  );
}
