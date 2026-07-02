import { useRef, useState } from 'react';
import * as api from '../api/client';
import { useConfirm } from '../components/ConfirmProvider';
import { useI18n } from '../i18n';

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
  const { t } = useI18n();
  const confirm = useConfirm();
  const [text, setText] = useState('');
  const [replace, setReplace] = useState(false);
  const [msg, setMsg] = useState('');
  const [err, setErr] = useState('');
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  async function doExport() {
    setErr('');
    setMsg('');
    setBusy(true);
    try {
      const data = await exportFn();
      setText(JSON.stringify(data, null, 2));
      setMsg(t('acc.json.exported', { n: Object.keys(data).length }));
    } catch (e) {
      setErr(e instanceof api.ApiError ? e.detail : t('acc.json.errorExport'));
    } finally {
      setBusy(false);
    }
  }

  async function doDownload() {
    setErr('');
    setMsg('');
    setBusy(true);
    try {
      const data = await exportFn();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${label.toLowerCase().replace(/\s+/g, '-')}.json`;
      // Firefox only honours .click() on anchors that are in the document.
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      setErr(e instanceof api.ApiError ? e.detail : t('acc.json.errorExport'));
    } finally {
      setBusy(false);
    }
  }

  function loadFromFile(file: File) {
    setErr('');
    setMsg('');
    const reader = new FileReader();
    // Only fills the textarea — the single import path below (parse +
    // replace-confirm + import) stays authoritative for file input too.
    reader.onload = () => setText(String(reader.result ?? ''));
    reader.onerror = () => setErr(t('acc.json.errorImport'));
    reader.readAsText(file);
  }

  async function doImport() {
    setErr('');
    setMsg('');
    let parsed: JsonMap;
    try {
      parsed = JSON.parse(text);
    } catch {
      setErr(t('acc.json.invalidJson'));
      return;
    }
    if (replace) {
      // Replacing wipes every existing entry — never on a bare click.
      const ok = await confirm({
        title: t('acc.json.confirmReplaceTitle'),
        message: t('acc.json.confirmReplaceMsg', { label }),
        confirmLabel: t('acc.json.import'),
        danger: true,
      });
      if (!ok) return;
    }
    setBusy(true);
    try {
      const res = await importFn(parsed, replace);
      setMsg(t('acc.json.imported', { n: res.imported }));
      onImported();
    } catch (e) {
      setErr(e instanceof api.ApiError ? e.detail : t('acc.json.errorImport'));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ marginTop: 18, borderTop: '1px solid #232833', paddingTop: 12 }}>
      <button className="acc-link" onClick={() => setOpen((o) => !o)}>
        {open ? '▾' : '▸'} {t('acc.json.toggle', { label })}
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
            <button className="acc-btn secondary" onClick={doExport} disabled={busy}>
              {t('acc.json.export')}
            </button>
            <button className="acc-btn secondary" onClick={doDownload} disabled={busy}>
              {t('acc.json.download')}
            </button>
            <button className="acc-btn secondary" onClick={() => fileInputRef.current?.click()} disabled={busy}>
              {t('acc.json.fromFile')}
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept=".json,application/json"
              style={{ display: 'none' }}
              data-testid="json-file-input"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) loadFromFile(file);
                e.target.value = '';
              }}
            />
            <button className="acc-btn" onClick={doImport} disabled={busy || !text.trim()}>
              {t('acc.json.import')}
            </button>
            <label className="acc-muted" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <input type="checkbox" checked={replace} onChange={(e) => setReplace(e.target.checked)} />
              {t('acc.json.replace')}
            </label>
          </div>
        </div>
      )}
    </div>
  );
}
