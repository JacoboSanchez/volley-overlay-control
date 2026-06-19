import { useCallback, useEffect, useState } from 'react';
import * as api from '../api/client';
import { useAuth } from '../auth/AuthContext';
import JsonImportExport from './JsonImportExport';

export default function PresetsPage() {
  const { ctx } = useAuth();
  const isAdmin = ctx?.user?.role === 'admin';
  const [items, setItems] = useState<api.PresetSummary[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    const res = await api.listPresets();
    setItems(res.items);
    setLoading(false);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function onDelete(p: api.PresetSummary) {
    if (p.source !== 'user') return;
    if (!confirm(`Delete preset "${p.name}"?`)) return;
    await api.deletePreset(p.slug);
    await load();
  }

  return (
    <div>
      <h2>Presets</h2>
      <p className="acc-muted">
        Global presets (curated by an administrator) and your own. Create new presets from a live
        scoreboard's customization panel; they appear across all your scoreboards.
      </p>
      {loading ? (
        <p className="acc-muted">Loading…</p>
      ) : items.length === 0 ? (
        <p className="acc-muted">No presets yet.</p>
      ) : (
        <table className="acc-table">
          <thead><tr><th>Name</th><th>Scope</th><th>Covers</th><th></th></tr></thead>
          <tbody>
            {items.map((p) => (
              <tr key={`${p.source}:${p.slug}`}>
                <td>{p.name}</td>
                <td><span className="acc-pill">{p.source}</span></td>
                <td className="acc-muted">{p.categories.join(', ')}</td>
                <td>
                  {p.source === 'user' ? (
                    <button className="acc-btn danger" onClick={() => onDelete(p)}>Delete</button>
                  ) : (
                    <span className="acc-muted">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {isAdmin && <AdminGlobalPresets onChange={load} />}
    </div>
  );
}

function AdminGlobalPresets({ onChange }: { onChange: () => void }) {
  const [globals, setGlobals] = useState<api.PresetSummary[]>([]);

  const load = useCallback(async () => {
    const res = await api.adminListGlobalPresets();
    setGlobals(res.items);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const refresh = useCallback(async () => {
    await load();
    onChange();
  }, [load, onChange]);

  async function toggle(p: api.PresetSummary) {
    await api.adminSetPresetActive(p.slug, !p.is_active);
    await refresh();
  }
  async function del(p: api.PresetSummary) {
    if (!confirm(`Delete global preset "${p.name}"?`)) return;
    await api.adminDeleteGlobalPreset(p.slug);
    await refresh();
  }

  return (
    <div style={{ marginTop: 34, borderTop: '1px solid #232833', paddingTop: 18 }}>
      <h3>Manage global presets (admin)</h3>
      <p className="acc-muted">
        Only <strong>active</strong> global presets are shown to users. Toggle activation, delete,
        or bulk-import an <code>APP_THEMES</code> JSON map.
      </p>
      {globals.length === 0 ? (
        <p className="acc-muted">No global presets yet — import some below.</p>
      ) : (
        <table className="acc-table">
          <thead><tr><th>Name</th><th>Active</th><th>Covers</th><th></th></tr></thead>
          <tbody>
            {globals.map((p) => (
              <tr key={p.slug}>
                <td>{p.name}</td>
                <td>
                  <span className="acc-pill" style={{ background: p.is_active ? '#1e4031' : '#3a2b1d' }}>
                    {p.is_active ? 'active' : 'inactive'}
                  </span>
                </td>
                <td className="acc-muted">{p.categories.join(', ')}</td>
                <td style={{ whiteSpace: 'nowrap' }}>
                  <button className="acc-btn ghost" onClick={() => toggle(p)}>
                    {p.is_active ? 'Deactivate' : 'Activate'}
                  </button>{' '}
                  <button className="acc-btn danger" onClick={() => del(p)}>Delete</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <JsonImportExport
        label="Global presets"
        exportFn={api.adminExportPresets}
        importFn={api.adminImportPresets}
        onImported={refresh}
      />
    </div>
  );
}
