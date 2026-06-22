import { useCallback, useEffect, useState } from 'react';
import * as api from '../api/client';
import { useAuth } from '../auth/AuthContext';
import EmptyState from '../components/EmptyState';
import { useToast } from '../components/Toast';
import { useConfirm } from '../components/ConfirmProvider';
import JsonImportExport from './JsonImportExport';

export default function PresetsPage() {
  const { ctx } = useAuth();
  const isAdmin = ctx?.user?.role === 'admin';
  const { toast } = useToast();
  const confirm = useConfirm();
  const [items, setItems] = useState<api.PresetSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      const res = await api.listPresets();
      setItems(res.items);
    } catch {
      setError('Could not load presets.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function onDelete(p: api.PresetSummary) {
    if (p.source !== 'user') return;
    const ok = await confirm({
      title: 'Delete preset',
      message: `Delete preset “${p.name}”?`,
      confirmLabel: 'Delete',
      danger: true,
    });
    if (!ok) return;
    try {
      await api.deletePreset(p.slug);
      await load();
      toast(`Deleted “${p.name}”.`);
    } catch (err) {
      toast(err instanceof api.ApiError ? err.detail : 'Could not delete preset.', 'error');
    }
  }

  return (
    <div>
      <h2>Presets</h2>
      <p className="acc-muted">
        Global presets (curated by an administrator) and your own. Create new presets from a live
        scoreboard’s customization panel; they appear across all your scoreboards.
      </p>
      {error && <div className="acc-error">{error}</div>}
      {loading ? (
        <p className="acc-muted">Loading…</p>
      ) : items.length === 0 ? (
        <EmptyState>
          No presets yet. Save a look from a live scoreboard’s customization panel and it will appear
          here, ready to reuse across all your scoreboards.
        </EmptyState>
      ) : (
        <table className="acc-table">
          <thead><tr>
            <th scope="col">Name</th><th scope="col">Scope</th>
            <th scope="col">Covers</th><th scope="col"></th>
          </tr></thead>
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
  const { toast } = useToast();
  const confirm = useConfirm();
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
    try {
      await api.adminSetPresetActive(p.slug, !p.is_active);
      await refresh();
      toast(p.is_active ? `“${p.name}” deactivated.` : `“${p.name}” activated.`);
    } catch (err) {
      toast(err instanceof api.ApiError ? err.detail : 'Could not update preset.', 'error');
    }
  }
  async function del(p: api.PresetSummary) {
    const ok = await confirm({
      title: 'Delete global preset',
      message: `Delete global preset “${p.name}”?`,
      confirmLabel: 'Delete',
      danger: true,
    });
    if (!ok) return;
    try {
      await api.adminDeleteGlobalPreset(p.slug);
      await refresh();
      toast(`Deleted “${p.name}”.`);
    } catch (err) {
      toast(err instanceof api.ApiError ? err.detail : 'Could not delete preset.', 'error');
    }
  }

  return (
    <div className="acc-section">
      <h3>Manage global presets (admin)</h3>
      <p className="acc-muted">
        Only <strong>active</strong> global presets are shown to users. Toggle activation, delete,
        or bulk-import an <code>APP_THEMES</code> JSON map.
      </p>
      {globals.length === 0 ? (
        <EmptyState>No global presets yet — import some below.</EmptyState>
      ) : (
        <table className="acc-table">
          <thead><tr>
            <th scope="col">Name</th><th scope="col">Active</th>
            <th scope="col">Covers</th><th scope="col"></th>
          </tr></thead>
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
