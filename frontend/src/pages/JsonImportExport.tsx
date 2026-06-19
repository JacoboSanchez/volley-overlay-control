import { useState } from 'react';

type JsonMap = Record<string, Record<string, unknown>>;

/** Admin JSON import/export panel — mirrors the APP_TEAMS / APP_THEMES shape so
 *  a config-provider configuration can be pasted in (or pulled out). */
export default function JsonImportExport({
  label,
  exportFn,
  importFn,
  onImported,
}: {
  label: string;
  exportFn: () => Promise<JsonMap>;
  importFn: (data: JsonMap, replace: boolean) => Promise<{ imported: number }>;
  onImported: () => void;
}) {
  const [text, setText] = useState('');
  const [replace, setReplace] = useState(false);
  const [msg, setMsg] = useState('');
  const [err, setErr] = useState('');
  const [open, setOpen] = useState(false);

  async function doExport() {
    setErr('');
    setMsg('');
    try {
      const data = await exportFn();
      setText(JSON.stringify(data, null, 2));
      setMsg(`Exported ${Object.keys(data).length} entries.`);
    } catch {
      setErr('Export failed.');
    }
  }

  async function doImport() {
    setErr('');
    setMsg('');
    let parsed: JsonMap;
    try {
      parsed = JSON.parse(text);
    } catch {
      setErr('That is not valid JSON.');
      return;
    }
    try {
      const res = await importFn(parsed, replace);
      setMsg(`Imported ${res.imported} entries.`);
      onImported();
    } catch {
      setErr('Import failed.');
    }
  }

  return (
    <div style={{ marginTop: 18, borderTop: '1px solid #232833', paddingTop: 12 }}>
      <button className="acc-link" onClick={() => setOpen((o) => !o)}>
        {open ? '▾' : '▸'} {label} (JSON import / export)
      </button>
      {open && (
        <div style={{ marginTop: 10 }}>
          {msg && <div className="acc-info">{msg}</div>}
          {err && <div className="acc-error">{err}</div>}
          <textarea
            className="acc-input"
            value={text}
            placeholder='{"Name": { … }}'
            onChange={(e) => setText(e.target.value)}
            rows={8}
            style={{ fontFamily: 'monospace', fontSize: '0.8rem', resize: 'vertical' }}
          />
          <div className="acc-btn-row">
            <button className="acc-btn secondary" onClick={doExport}>Export</button>
            <button className="acc-btn" onClick={doImport} disabled={!text.trim()}>Import</button>
            <label className="acc-muted" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <input type="checkbox" checked={replace} onChange={(e) => setReplace(e.target.checked)} />
              Replace existing
            </label>
          </div>
        </div>
      )}
    </div>
  );
}
