import { FormEvent, useCallback, useEffect, useState } from 'react';
import * as api from '../api/client';
import CopyField from '../components/CopyField';
import EmptyState from '../components/EmptyState';

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
      setError(err instanceof api.ApiError ? err.detail : 'Could not create overlay.');
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
        Each overlay is a scoreboard you control. To put it on stream, copy its <strong>OBS output
        URL</strong> below and add it in OBS as a <strong>Browser Source</strong>.
      </p>

      <form className="acc-form" onSubmit={onCreate}>
        <label className="acc-field">
          <span>Overlay id</span>
          <input className="acc-input" value={oid} placeholder="e.g. liga"
            onChange={(e) => setOid(e.target.value)} />
          <small className="acc-muted">Letters, digits, <code>. _ -</code> — no spaces.</small>
        </label>
        <label className="acc-field">
          <span>Display name (optional)</span>
          <input className="acc-input" value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="acc-field">
          <span>Format</span>
          <select className="acc-input" value={sets} onChange={(e) => setSets(e.target.value)}>
            <option value="">Default</option>
            <option value="3">Best of 3</option>
            <option value="5">Best of 5</option>
            <option value="1">Single set</option>
          </select>
        </label>
        <label className="acc-field">
          <span>Output URL (cloud, optional)</span>
          <input className="acc-input" value={outputUrl} placeholder="https://app.overlays.uno/output/…"
            onChange={(e) => setOutputUrl(e.target.value)} />
          <small className="acc-muted">Leave blank to use this app’s built-in OBS overlay URL.</small>
        </label>
        <div className="acc-form-actions">
          <span className="acc-form-spacer" aria-hidden="true">&nbsp;</span>
          <button className="acc-btn" type="submit" disabled={!oid.trim()}>Add overlay</button>
        </div>
      </form>
      {error && <div className="acc-error">{error}</div>}

      {loading ? (
        <p className="acc-muted">Loading…</p>
      ) : overlays.length === 0 ? (
        <EmptyState>No overlays yet — add one above to create your first scoreboard.</EmptyState>
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

      <ControlLink o={o} onChanged={onSaved} />
      <BookmarkLink o={o} onChanged={onSaved} />
    </div>
  );
}

function BookmarkLink({ o, onChanged }: { o: api.OverlayPayload; onChanged: () => void }) {
  const [busy, setBusy] = useState(false);

  async function toggle() {
    if (!o.public_control && !confirm(
      'Enable a permanent no-login control URL for this board?\n\n' +
      'The link is based on your username and this overlay id, so it is ' +
      'guessable — anyone who works it out could control this scoreboard. ' +
      'Use it as your own bookmark; share the operator link above instead.',
    )) {
      return;
    }
    setBusy(true);
    try {
      await api.updateOverlay(o.oid, { public_control: !o.public_control });
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="acc-section" style={{ marginTop: 18, maxWidth: 560 }}>
      <h4 style={{ margin: '0 0 4px' }}>Permanent bookmark link (username + id)</h4>
      <p className="acc-muted" style={{ marginTop: 0 }}>
        A stable, no-login URL you can bookmark forever. It never changes — but it’s
        <strong> guessable</strong> (your username + this id), so keep it to yourself and use the
        revocable operator link above for sharing.
      </p>
      <label className="acc-muted" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <input type="checkbox" checked={o.public_control} disabled={busy} onChange={toggle} />
        Allow controlling this board from its username + id URL without logging in
      </label>
      {o.public_control && o.public_control_url && (
        <div style={{ marginTop: 10 }}>
          <CopyField value={o.public_control_url} label="Permanent bookmark link" />
        </div>
      )}
    </div>
  );
}

function ControlLink({ o, onChanged }: { o: api.OverlayPayload; onChanged: () => void }) {
  const [busy, setBusy] = useState(false);

  async function regenerate() {
    if (!confirm('Generate a new control link? The current link will stop working immediately.')) {
      return;
    }
    setBusy(true);
    try {
      await api.regenerateControlToken(o.oid);
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="acc-section" style={{ marginTop: 18, maxWidth: 560 }}>
      <h4 style={{ margin: '0 0 4px' }}>Operator control link</h4>
      <p className="acc-muted" style={{ marginTop: 0 }}>
        Anyone with this link can run this scoreboard — no login needed. Hand it to whoever is
        tracking the match. Regenerate it to revoke a link you’ve shared.
      </p>
      {o.control_url ? (
        <CopyField value={o.control_url} label="Operator control link" />
      ) : (
        <span className="acc-muted">No link yet — generate one.</span>
      )}
      <div style={{ marginTop: 10 }}>
        <button className="acc-btn ghost" onClick={regenerate} disabled={busy}>
          {busy ? 'Working…' : o.control_url ? 'Regenerate link' : 'Generate link'}
        </button>
      </div>
    </div>
  );
}
