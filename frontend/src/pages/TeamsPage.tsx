import { FormEvent, useCallback, useEffect, useState } from 'react';
import * as api from '../api/client';
import { useAuth } from '../auth/AuthContext';
import EmptyState from '../components/EmptyState';
import JsonImportExport from './JsonImportExport';

function useSelection() {
  const [sel, setSel] = useState<Set<number>>(new Set());
  const toggle = useCallback((id: number) => {
    setSel((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }, []);
  const clear = useCallback(() => setSel(new Set()), []);
  return { sel, toggle, clear };
}

export default function TeamsPage() {
  const { ctx } = useAuth();
  const isAdmin = ctx?.user?.role === 'admin';
  const [mine, setMine] = useState<api.TeamOut[]>([]);
  const [catalog, setCatalog] = useState<api.TeamOut[]>([]);
  const [groups, setGroups] = useState<api.TeamGroupOut[]>([]);
  const [editing, setEditing] = useState<number | null>(null);
  const [loadError, setLoadError] = useState('');

  const mineSel = useSelection();
  const catSel = useSelection();

  const load = useCallback(async () => {
    try {
      const [m, c, g] = await Promise.all([
        api.getMyTeams(),
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

  const reload = useCallback(async () => {
    mineSel.clear();
    catSel.clear();
    setEditing(null);
    await load();
  }, [load, mineSel, catSel]);

  const mineNames = new Set(mine.map((t) => t.name));
  // Catalog teams not yet in the user's list (by name).
  const addable = catalog.filter((t) => !mineNames.has(t.name));

  async function removeSelectedMine() {
    if (mineSel.sel.size === 0) return;
    await api.removeTeamsFromMine([...mineSel.sel]);
    await reload();
  }
  async function addSelectedCatalog() {
    if (catSel.sel.size === 0) return;
    await api.addTeamsToMine([...catSel.sel]);
    await reload();
  }
  async function copyGroup(id: number) {
    await api.copyGroupToMine(id);
    await reload();
  }

  return (
    <div>
      <h2>Teams</h2>
      {loadError && <div className="acc-error">{loadError}</div>}
      <p className="acc-muted">
        Your team list appears in the scoreboard team picker. It starts from the global catalog —
        add or remove catalog teams, copy a whole group, or create your own custom teams.
      </p>

      <h3 className="acc-subhead">My teams</h3>
      {mine.length === 0 ? (
        <EmptyState>No teams yet — add some from the catalog below or create a custom one.</EmptyState>
      ) : (
        <>
          <div className="acc-row" style={{ marginBottom: 8 }}>
            <button className="acc-btn danger" disabled={mineSel.sel.size === 0}
              onClick={removeSelectedMine}>
              Remove selected ({mineSel.sel.size})
            </button>
          </div>
          <table className="acc-table">
            <thead><tr><th></th><th>Team</th><th></th></tr></thead>
            <tbody>
              {mine.map((t) => (
                <MyTeamRow
                  key={t.id} t={t}
                  selected={mineSel.sel.has(t.id)} onToggle={() => mineSel.toggle(t.id)}
                  editing={editing === t.id}
                  onEdit={() => setEditing(editing === t.id ? null : t.id)}
                  onChanged={reload}
                />
              ))}
            </tbody>
          </table>
        </>
      )}

      <CustomTeamForm onCreated={reload} />

      {groups.length > 0 && (
        <>
          <h3 className="acc-subhead">Team groups</h3>
          {groups.map((g) => (
            <div key={g.id} style={{ marginBottom: 10 }}>
              <button className="acc-btn secondary" onClick={() => copyGroup(g.id)}>
                Copy “{g.name}” ({g.teams.length})
              </button>
            </div>
          ))}
        </>
      )}

      <h3 className="acc-subhead">Catalog</h3>
      {addable.length === 0 ? (
        <EmptyState>Every catalog team is already in your list.</EmptyState>
      ) : (
        <>
          <div className="acc-row" style={{ marginBottom: 8 }}>
            <button className="acc-btn" disabled={catSel.sel.size === 0} onClick={addSelectedCatalog}>
              Add selected ({catSel.sel.size})
            </button>
          </div>
          <table className="acc-table">
            <thead><tr><th></th><th>Team</th></tr></thead>
            <tbody>
              {addable.map((t) => (
                <tr key={t.id}>
                  <td>
                    <input type="checkbox" aria-label={`Select ${t.name}`}
                      checked={catSel.sel.has(t.id)} onChange={() => catSel.toggle(t.id)} />
                  </td>
                  <td><TeamSwatch t={t} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {isAdmin && <AdminCatalog catalog={catalog} onChange={load} />}
    </div>
  );
}

function MyTeamRow({
  t, selected, onToggle, editing, onEdit, onChanged,
}: {
  t: api.TeamOut;
  selected: boolean;
  onToggle: () => void;
  editing: boolean;
  onEdit: () => void;
  onChanged: () => void;
}) {
  return (
    <>
      <tr>
        <td>
          <input type="checkbox" aria-label={`Select ${t.name}`}
            checked={selected} onChange={onToggle} />
        </td>
        <td>
          <TeamSwatch t={t} />
          {!t.is_global && <span className="acc-pill" style={{ marginLeft: 8 }}>custom</span>}
        </td>
        <td style={{ whiteSpace: 'nowrap' }}>
          {!t.is_global && (
            <button className="acc-btn ghost" onClick={onEdit}>{editing ? 'Close' : 'Edit'}</button>
          )}
        </td>
      </tr>
      {editing && !t.is_global && (
        <tr>
          <td colSpan={3}><CustomTeamEditor t={t} onSaved={onChanged} /></td>
        </tr>
      )}
    </>
  );
}

function CustomTeamForm({ onCreated }: { onCreated: () => void }) {
  const [name, setName] = useState('');
  const [icon, setIcon] = useState('');
  const [color, setColor] = useState('#1565c0');
  const [textColor, setTextColor] = useState('#ffffff');
  const [error, setError] = useState('');

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    setError('');
    try {
      await api.createMyTeam({ name: name.trim(), icon: icon.trim() || null, color, text_color: textColor });
      setName('');
      setIcon('');
      onCreated();
    } catch (err) {
      setError(err instanceof api.ApiError ? err.detail : 'Could not create team.');
    }
  }

  return (
    <div className="acc-section">
      <h3>Create a custom team</h3>
      <p className="acc-muted">
        Your own teams live only in your list (not the global catalog). Removing one deletes it.
      </p>
      <form className="acc-form" onSubmit={onCreate}>
        <label className="acc-field">
          <span>Name</span>
          <input className="acc-input" value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="acc-field">
          <span>Logo URL (optional)</span>
          <input className="acc-input" value={icon} placeholder="https://…/logo.png"
            onChange={(e) => setIcon(e.target.value)} />
        </label>
        <label className="acc-field" style={{ flex: '0 0 auto' }}>
          <span>Colour</span>
          <input type="color" className="acc-color" value={color}
            onChange={(e) => setColor(e.target.value)} />
        </label>
        <label className="acc-field" style={{ flex: '0 0 auto' }}>
          <span>Text colour</span>
          <input type="color" className="acc-color" value={textColor}
            onChange={(e) => setTextColor(e.target.value)} />
        </label>
        <div className="acc-form-actions">
          <span className="acc-form-spacer" aria-hidden="true">&nbsp;</span>
          <button className="acc-btn" type="submit" disabled={!name.trim()}>Add team</button>
        </div>
      </form>
      {error && <div className="acc-error">{error}</div>}
    </div>
  );
}

function CustomTeamEditor({ t, onSaved }: { t: api.TeamOut; onSaved: () => void }) {
  const [name, setName] = useState(t.name);
  const [icon, setIcon] = useState(t.icon || '');
  const [color, setColor] = useState(hex(t.color, '#1565c0'));
  const [textColor, setTextColor] = useState(hex(t.text_color, '#ffffff'));
  const [saved, setSaved] = useState(false);

  async function save() {
    await api.updateMyTeam(t.id, {
      name: name.trim() || undefined,
      icon: icon.trim() || null,
      color,
      text_color: textColor,
    });
    setSaved(true);
    setTimeout(() => setSaved(false), 1200);
    onSaved();
  }

  return (
    <div style={{ background: '#14171d', borderRadius: 10, padding: 14, margin: '6px 0' }}>
      <div className="acc-row" style={{ marginBottom: 8 }}>
        <label className="acc-field" style={{ marginBottom: 0 }}>
          <span>Name</span>
          <input className="acc-input" value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="acc-field" style={{ marginBottom: 0, minWidth: 200 }}>
          <span>Logo URL</span>
          <input className="acc-input" value={icon} placeholder="https://…/logo.png"
            onChange={(e) => setIcon(e.target.value)} />
        </label>
        <label className="acc-field" style={{ marginBottom: 0 }}>
          <span>Colour</span>
          <input type="color" className="acc-color sm" value={color}
            onChange={(e) => setColor(e.target.value)} />
        </label>
        <label className="acc-field" style={{ marginBottom: 0 }}>
          <span>Text</span>
          <input type="color" className="acc-color sm" value={textColor}
            onChange={(e) => setTextColor(e.target.value)} />
        </label>
      </div>
      <button className="acc-btn" onClick={save}>{saved ? 'Saved!' : 'Save'}</button>
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
      setError(err instanceof api.ApiError ? err.detail : 'Could not create team.');
    }
  }

  return (
    <div className="acc-section">
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
          <input type="color" className="acc-color" value={color}
            onChange={(e) => setColor(e.target.value)} />
        </label>
        <label className="acc-field" style={{ marginBottom: 0 }}>
          <span>Text colour</span>
          <input type="color" className="acc-color" value={textColor}
            onChange={(e) => setTextColor(e.target.value)} />
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
        <input type="color" className="acc-color sm" value={color}
          onChange={(e) => setColor(e.target.value)} />
      </td>
      <td>
        <input type="color" className="acc-color sm" value={textColor}
          onChange={(e) => setTextColor(e.target.value)} />
      </td>
      <td style={{ whiteSpace: 'nowrap' }}>
        <button className="acc-btn" onClick={save}>{saved ? 'Saved!' : 'Save'}</button>{' '}
        <button className="acc-btn danger" onClick={del}>Delete</button>
      </td>
    </tr>
  );
}
