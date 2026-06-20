import { FormEvent, useCallback, useEffect, useState } from 'react';
import * as api from '../api/client';

export default function OverlaysPage() {
  const [overlays, setOverlays] = useState<api.OverlayPayload[]>([]);
  const [oid, setOid] = useState('');
  const [name, setName] = useState('');
  const [sets, setSets] = useState('');
  const [outputUrl, setOutputUrl] = useState('');
  const [error, setError] = useState('');
  const [copied, setCopied] = useState('');
  const [editing, setEditing] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      setOverlays(await api.getOverlays());
    } catch {
      setError('Could not load your overlays.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    setError('');
    try {
      await api.createOverlay(oid.trim(), {
        display_name: name.trim() || null,
        output_url: outputUrl.trim() || null,
        sets: sets ? Number(sets) : null,
      });
      setOid('');
      setName('');
      setSets('');
      setOutputUrl('');
      await load();
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message.replace(/^API.*?: /, '') : 'Could not create overlay.');
    }
  }

  async function onDelete(o: api.OverlayPayload) {
    if (!confirm(`Delete overlay "${o.oid}"? This removes its scoreboard state and reports.`)) return;
    await api.deleteOverlay(o.oid);
    await load();
  }

  async function copy(url: string) {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(url);
      setTimeout(() => setCopied(''), 1500);
    } catch {
      /* ignore */
    }
  }

  return (
    <div>
      <h2>My overlays</h2>
      <p className="acc-muted">
        Each overlay is a scoreboard you control. Add one in OBS using its output URL.
      </p>

      <form className="acc-row" onSubmit={onCreate} style={{ marginTop: 16 }}>
        <label className="acc-field" style={{ marginBottom: 0 }}>
          <span>Overlay id</span>
          <input className="acc-input" value={oid} placeholder="e.g. liga"
            onChange={(e) => setOid(e.target.value)} />
        </label>
        <label className="acc-field" style={{ marginBottom: 0 }}>
          <span>Display name (optional)</span>
          <input className="acc-input" value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="acc-field" style={{ marginBottom: 0 }}>
          <span>Format</span>
          <select className="acc-input" value={sets} onChange={(e) => setSets(e.target.value)}>
            <option value="">Default</option>
            <option value="3">Best of 3</option>
            <option value="5">Best of 5</option>
            <option value="1">Single set</option>
          </select>
        </label>
        <label className="acc-field" style={{ marginBottom: 0, minWidth: 200 }}>
          <span>Output URL (cloud, optional)</span>
          <input className="acc-input" value={outputUrl} placeholder="https://app.overlays.uno/output/…"
            onChange={(e) => setOutputUrl(e.target.value)} />
        </label>
        <button className="acc-btn" type="submit" disabled={!oid.trim()}>Add overlay</button>
      </form>
      {error && <div className="acc-error">{error}</div>}

      {loading ? (
        <p className="acc-muted">Loading…</p>
      ) : overlays.length === 0 ? (
        <p className="acc-muted">No overlays yet — add one above.</p>
      ) : (
        <table className="acc-table">
          <thead>
            <tr><th>Overlay</th><th>OBS output URL</th><th>Format</th><th></th></tr>
          </thead>
          <tbody>
            {overlays.map((o) => (
              <OverlayRow
                key={o.oid}
                o={o}
                editing={editing === o.oid}
                onEdit={() => setEditing(editing === o.oid ? null : o.oid)}
                onSaved={async () => { setEditing(null); await load(); }}
                onDelete={() => onDelete(o)}
                onCopy={() => copy(o.output_url)}
                copied={copied === o.output_url}
              />
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function formatLabel(sets: number | null): string {
  if (sets === 1) return 'Single set';
  if (sets) return `Best of ${sets}`;
  return 'Default';
}

function OverlayRow({
  o, editing, onEdit, onSaved, onDelete, onCopy, copied,
}: {
  o: api.OverlayPayload;
  editing: boolean;
  onEdit: () => void;
  onSaved: () => void;
  onDelete: () => void;
  onCopy: () => void;
  copied: boolean;
}) {
  return (
    <>
      <tr>
        <td>
          <strong>{o.oid}</strong>
          {o.display_name && <div className="acc-muted">{o.display_name}</div>}
        </td>
        <td><code style={{ fontSize: '0.8rem', wordBreak: 'break-all' }}>{o.output_url}</code></td>
        <td className="acc-muted">{formatLabel(o.sets)}</td>
        <td style={{ whiteSpace: 'nowrap' }}>
          <a className="acc-btn" href={`/board?oid=${encodeURIComponent(o.oid)}`}>Open</a>{' '}
          <button className="acc-btn ghost" onClick={onCopy}>{copied ? 'Copied!' : 'Copy URL'}</button>{' '}
          <button className="acc-btn ghost" onClick={onEdit}>{editing ? 'Close' : 'Edit'}</button>{' '}
          <button className="acc-btn danger" onClick={onDelete}>Delete</button>
        </td>
      </tr>
      {editing && (
        <tr>
          <td colSpan={4}><OverlayEditor o={o} onSaved={onSaved} /></td>
        </tr>
      )}
    </>
  );
}

function OverlayEditor({ o, onSaved }: { o: api.OverlayPayload; onSaved: () => void }) {
  const [name, setName] = useState(o.display_name || '');
  const [sets, setSets] = useState(o.sets ? String(o.sets) : '');
  const [points, setPoints] = useState(o.points ? String(o.points) : '');
  const [lastSet, setLastSet] = useState(o.points_last_set ? String(o.points_last_set) : '');
  const [outputUrl, setOutputUrl] = useState(o.custom_output_url || '');

  async function save() {
    await api.updateOverlay(o.oid, {
      display_name: name.trim() || null,
      output_url: outputUrl.trim() || null,
      sets: sets ? Number(sets) : null,
      points: points ? Number(points) : null,
      points_last_set: lastSet ? Number(lastSet) : null,
    });
    onSaved();
  }

  return (
    <div style={{ background: '#14171d', borderRadius: 10, padding: 14, margin: '6px 0' }}>
      <div className="acc-row" style={{ marginBottom: 8 }}>
        <label className="acc-field" style={{ marginBottom: 0 }}>
          <span>Display name</span>
          <input className="acc-input" value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="acc-field" style={{ marginBottom: 0 }}>
          <span>Format</span>
          <select className="acc-input" value={sets} onChange={(e) => setSets(e.target.value)}>
            <option value="">Default</option>
            <option value="1">Single set</option>
            <option value="3">Best of 3</option>
            <option value="5">Best of 5</option>
          </select>
        </label>
        <label className="acc-field" style={{ marginBottom: 0, maxWidth: 110 }}>
          <span>Points/set</span>
          <input className="acc-input" type="number" value={points} placeholder="25"
            onChange={(e) => setPoints(e.target.value)} />
        </label>
        <label className="acc-field" style={{ marginBottom: 0, maxWidth: 130 }}>
          <span>Last-set points</span>
          <input className="acc-input" type="number" value={lastSet} placeholder="15"
            onChange={(e) => setLastSet(e.target.value)} />
        </label>
      </div>
      <label className="acc-field" style={{ maxWidth: 480 }}>
        <span>Output URL (cloud / custom — blank = local OBS URL above)</span>
        <input className="acc-input" value={outputUrl} placeholder="https://app.overlays.uno/output/…"
          onChange={(e) => setOutputUrl(e.target.value)} />
      </label>
      <button className="acc-btn" onClick={save}>Save settings</button>
    </div>
  );
}
