import { useCallback, useEffect, useState } from 'react';
import * as api from '../api/client';

export default function PresetsPage() {
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
    </div>
  );
}
