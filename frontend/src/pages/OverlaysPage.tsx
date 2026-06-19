import { FormEvent, useCallback, useEffect, useState } from 'react';
import * as api from '../api/client';

export default function OverlaysPage() {
  const [overlays, setOverlays] = useState<api.OverlayPayload[]>([]);
  const [oid, setOid] = useState('');
  const [name, setName] = useState('');
  const [error, setError] = useState('');
  const [copied, setCopied] = useState('');
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setOverlays(await api.getOverlays());
    setLoading(false);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    setError('');
    try {
      await api.createOverlay(oid.trim(), name.trim() || undefined);
      setOid('');
      setName('');
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
          <input className="acc-input" value={name}
            onChange={(e) => setName(e.target.value)} />
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
            <tr><th>Overlay</th><th>OBS output URL</th><th></th></tr>
          </thead>
          <tbody>
            {overlays.map((o) => (
              <tr key={o.oid}>
                <td>
                  <strong>{o.oid}</strong>
                  {o.display_name && <div className="acc-muted">{o.display_name}</div>}
                </td>
                <td>
                  <code style={{ fontSize: '0.8rem', wordBreak: 'break-all' }}>{o.output_url}</code>
                </td>
                <td style={{ whiteSpace: 'nowrap' }}>
                  <a className="acc-btn" href={`/board?oid=${encodeURIComponent(o.oid)}`}>Open</a>{' '}
                  <button className="acc-btn ghost" onClick={() => copy(o.output_url)}>
                    {copied === o.output_url ? 'Copied!' : 'Copy URL'}
                  </button>{' '}
                  <button className="acc-btn danger" onClick={() => onDelete(o)}>Delete</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
