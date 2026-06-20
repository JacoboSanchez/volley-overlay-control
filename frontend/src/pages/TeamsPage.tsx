import { FormEvent, useCallback, useEffect, useState } from 'react';
import * as api from '../api/client';
import { useAuth } from '../auth/AuthContext';
import JsonImportExport from './JsonImportExport';

export default function TeamsPage() {
  const { ctx } = useAuth();
  const isAdmin = ctx?.user?.role === 'admin';
  const [mine, setMine] = useState<Record<string, unknown>>({});
  const [catalog, setCatalog] = useState<api.TeamOut[]>([]);
  const [groups, setGroups] = useState<api.TeamGroupOut[]>([]);
  const [loadError, setLoadError] = useState('');

  const load = useCallback(async () => {
    try {
      const [m, c, g] = await Promise.all([
        api.getTeams(),
        api.getTeamCatalog(),
        api.getTeamGroups(),
      ]);
      setMine(m);
      setCatalog(c);
      setGroups(g);
    } catch {
      setLoadError('Could not load teams.');
    }
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
      {loadError && <div className="acc-error">{loadError}</div>}
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

      {isAdmin && <AdminCatalog catalog={catalog} onChange={load} />}
    </div>
  );
}

function TeamSwatch({ t }: { t: api.TeamOut }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 10 }}>
      <span
        style={{
          width: 26, height: 26, borderRadius: 5, flex: '0 0 auto',
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          background: t.color || '#444', color: t.text_color || '#fff',
          border: '1px solid #333', overflow: 'hidden', fontSize: 11, fontWeight: 700,
        }}
        title={`bg ${t.color || '—'} / text ${t.text_color || '—'}`}
      >
        {t.icon ? (
          <img src={t.icon} alt="" style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
        ) : (
          (t.name[0] || '?').toUpperCase()
        )}
      </span>
      {t.name}
    </span>
  );
}

function hex(value: string | null | undefined, fallback: string): string {
  return value && /^#[0-9a-fA-F]{6}$/.test(value) ? value : fallback;
}

function AdminCatalog({ catalog, onChange }: { catalog: api.TeamOut[]; onChange: () => void }) {
  const [name, setName] = useState('');
  const [icon, setIcon] = useState('');
  const [color, setColor] = useState('#1565c0');
  const [textColor, setTextColor] = useState('#ffffff');
  const [error, setError] = useState('');

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    setError('');
    try {
      await api.adminCreateTeam({ name: name.trim(), icon: icon.trim() || null, color, text_color: textColor });
      setName('');
      setIcon('');
      await onChange();
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message.replace(/^API.*?: /, '') : 'Could not create team.');
    }
  }

  return (
    <div style={{ marginTop: 34, borderTop: '1px solid #232833', paddingTop: 18 }}>
      <h3>Manage catalog (admin)</h3>
      <p className="acc-muted">
        Configure the preloaded teams users can add: name, logo URL, background colour and text
        colour.
      </p>

      <form className="acc-row" onSubmit={onCreate}>
        <label className="acc-field" style={{ marginBottom: 0 }}>
          <span>Name</span>
          <input className="acc-input" value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="acc-field" style={{ marginBottom: 0, minWidth: 220 }}>
          <span>Logo URL</span>
          <input className="acc-input" value={icon} placeholder="https://…/logo.png"
            onChange={(e) => setIcon(e.target.value)} />
        </label>
        <label className="acc-field" style={{ marginBottom: 0 }}>
          <span>Colour</span>
          <input type="color" value={color} onChange={(e) => setColor(e.target.value)}
            style={{ width: 48, height: 38, background: 'none', border: 'none' }} />
        </label>
        <label className="acc-field" style={{ marginBottom: 0 }}>
          <span>Text colour</span>
          <input type="color" value={textColor} onChange={(e) => setTextColor(e.target.value)}
            style={{ width: 48, height: 38, background: 'none', border: 'none' }} />
        </label>
        <button className="acc-btn" type="submit" disabled={!name.trim()}>Add team</button>
      </form>
      {error && <div className="acc-error">{error}</div>}

      <table className="acc-table">
        <thead>
          <tr><th>Team</th><th>Logo URL</th><th>Colour</th><th>Text</th><th></th></tr>
        </thead>
        <tbody>
          {catalog.map((t) => (
            <AdminTeamRow key={t.id} team={t} onChange={onChange} />
          ))}
        </tbody>
      </table>

      <JsonImportExport
        label="Team catalog"
        exportFn={api.adminExportTeams}
        importFn={api.adminImportTeams}
        onImported={onChange}
      />
    </div>
  );
}

function AdminTeamRow({ team, onChange }: { team: api.TeamOut; onChange: () => void }) {
  const [icon, setIcon] = useState(team.icon || '');
  const [color, setColor] = useState(hex(team.color, '#1565c0'));
  const [textColor, setTextColor] = useState(hex(team.text_color, '#ffffff'));
  const [saved, setSaved] = useState(false);

  async function save() {
    await api.adminUpdateTeam(team.id, { icon: icon.trim() || null, color, text_color: textColor });
    setSaved(true);
    setTimeout(() => setSaved(false), 1200);
    await onChange();
  }
  async function del() {
    if (!confirm(`Delete team "${team.name}" from the catalog?`)) return;
    await api.adminDeleteTeam(team.id);
    await onChange();
  }

  return (
    <tr>
      <td><TeamSwatch t={{ ...team, color, text_color: textColor, icon: icon || null }} /></td>
      <td>
        <input className="acc-input" value={icon} placeholder="https://…/logo.png"
          onChange={(e) => setIcon(e.target.value)} style={{ minWidth: 200 }} />
      </td>
      <td>
        <input type="color" value={color} onChange={(e) => setColor(e.target.value)}
          style={{ width: 42, height: 32, background: 'none', border: 'none' }} />
      </td>
      <td>
        <input type="color" value={textColor} onChange={(e) => setTextColor(e.target.value)}
          style={{ width: 42, height: 32, background: 'none', border: 'none' }} />
      </td>
      <td style={{ whiteSpace: 'nowrap' }}>
        <button className="acc-btn" onClick={save}>{saved ? 'Saved!' : 'Save'}</button>{' '}
        <button className="acc-btn danger" onClick={del}>Delete</button>
      </td>
    </tr>
  );
}
