import { useCallback, useEffect, useState } from 'react';
import * as api from '../api/client';

export default function TeamsPage() {
  const [mine, setMine] = useState<Record<string, unknown>>({});
  const [catalog, setCatalog] = useState<api.TeamOut[]>([]);
  const [groups, setGroups] = useState<api.TeamGroupOut[]>([]);

  const load = useCallback(async () => {
    const [m, c, g] = await Promise.all([
      api.getTeams(),
      api.getTeamCatalog(),
      api.getTeamGroups(),
    ]);
    setMine(m);
    setCatalog(c);
    setGroups(g);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const mineNames = new Set(Object.keys(mine));

  async function addTeam(id: number) {
    await api.addTeamsToMine([id]);
    await load();
  }
  async function removeTeam(id: number) {
    await api.removeTeamFromMine(id);
    await load();
  }
  async function copyGroup(id: number) {
    await api.copyGroupToMine(id);
    await load();
  }

  return (
    <div>
      <h2>Teams</h2>
      <p className="acc-muted">
        Your team list appears in the scoreboard team picker. Add teams from the global catalog or
        copy a whole group.
      </p>

      <h3 style={{ marginTop: 20 }}>My teams</h3>
      {mineNames.size === 0 ? (
        <p className="acc-muted">No teams yet — add some from the catalog below.</p>
      ) : (
        <table className="acc-table">
          <thead><tr><th>Team</th><th></th></tr></thead>
          <tbody>
            {catalog
              .filter((t) => mineNames.has(t.name))
              .map((t) => (
                <tr key={t.id}>
                  <td><TeamSwatch t={t} /></td>
                  <td><button className="acc-btn ghost" onClick={() => removeTeam(t.id)}>Remove</button></td>
                </tr>
              ))}
          </tbody>
        </table>
      )}

      {groups.length > 0 && (
        <>
          <h3 style={{ marginTop: 24 }}>Team groups</h3>
          {groups.map((g) => (
            <div key={g.id} style={{ marginBottom: 10 }}>
              <button className="acc-btn secondary" onClick={() => copyGroup(g.id)}>
                Copy “{g.name}” ({g.teams.length})
              </button>
            </div>
          ))}
        </>
      )}

      <h3 style={{ marginTop: 24 }}>Catalog</h3>
      <table className="acc-table">
        <thead><tr><th>Team</th><th></th></tr></thead>
        <tbody>
          {catalog.map((t) => (
            <tr key={t.id}>
              <td><TeamSwatch t={t} /></td>
              <td>
                {mineNames.has(t.name) ? (
                  <span className="acc-pill">in your list</span>
                ) : (
                  <button className="acc-btn" onClick={() => addTeam(t.id)}>Add</button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TeamSwatch({ t }: { t: api.TeamOut }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
      <span
        style={{
          width: 14, height: 14, borderRadius: 3,
          background: t.color || '#666', border: '1px solid #333',
        }}
      />
      {t.name}
    </span>
  );
}
