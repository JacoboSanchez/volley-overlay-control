import { FormEvent, useCallback, useEffect, useState } from 'react';
import * as api from '../api/client';
import CopyField from '../components/CopyField';
import EmptyState from '../components/EmptyState';
import { useToast } from '../components/Toast';
import { useConfirm } from '../components/ConfirmProvider';
import { useI18n } from '../i18n';

export default function OverlaysPage() {
  const { t } = useI18n();
  const { toast } = useToast();
  const confirm = useConfirm();
  const [overlays, setOverlays] = useState<api.OverlayPayload[]>([]);
  const [oid, setOid] = useState('');
  const [name, setName] = useState('');
  const [sets, setSets] = useState('');
  const [error, setError] = useState('');
  const [copied, setCopied] = useState('');
  const [editing, setEditing] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      setOverlays(await api.getOverlays());
    } catch {
      setError(t('acc.reports.errorOverlays'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    setError('');
    try {
      const created = oid.trim();
      await api.createOverlay(created, {
        display_name: name.trim() || null,
        sets: sets ? Number(sets) : null,
      });
      setOid('');
      setName('');
      setSets('');
      await load();
      toast(t('acc.overlays.toastCreated', { oid: created }));
    } catch (err) {
      setError(err instanceof api.ApiError ? err.detail : t('acc.overlays.errorCreate'));
    }
  }

  async function onDelete(o: api.OverlayPayload) {
    const ok = await confirm({
      title: t('acc.overlays.confirmDeleteTitle'),
      message: t('acc.overlays.confirmDeleteMsg', { oid: o.oid }),
      confirmLabel: t('acc.common.delete'),
      danger: true,
    });
    if (!ok) return;
    try {
      await api.deleteOverlay(o.oid);
      await load();
      toast(t('acc.overlays.toastDeleted', { oid: o.oid }));
    } catch (err) {
      toast(err instanceof api.ApiError ? err.detail : t('acc.overlays.errorDelete'), 'error');
    }
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
      <h2>{t('acc.nav.overlays')}</h2>
      <p className="acc-muted">{t('acc.overlays.intro')}</p>

      <form className="acc-form" onSubmit={onCreate}>
        <label className="acc-field">
          <span>{t('acc.overlays.field.oid')}</span>
          <input className="acc-input" value={oid} placeholder={t('acc.overlays.field.oidPlaceholder')}
            onChange={(e) => setOid(e.target.value)} />
          <small className="acc-muted">{t('acc.overlays.field.oidHelp')}</small>
        </label>
        <label className="acc-field">
          <span>{t('acc.overlays.field.displayName')}</span>
          <input className="acc-input" value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="acc-field">
          <span>{t('acc.overlays.field.format')}</span>
          <select className="acc-input" value={sets} onChange={(e) => setSets(e.target.value)}>
            <option value="">{t('acc.format.default')}</option>
            <option value="3">{t('acc.format.bo3')}</option>
            <option value="5">{t('acc.format.bo5')}</option>
            <option value="1">{t('acc.format.single')}</option>
          </select>
        </label>
        <div className="acc-form-actions">
          <span className="acc-form-spacer" aria-hidden="true">&nbsp;</span>
          <button className="acc-btn" type="submit" disabled={!oid.trim()}>{t('acc.overlays.add')}</button>
        </div>
      </form>
      {error && <div className="acc-error">{error}</div>}

      {loading ? (
        <p className="acc-muted">{t('acc.common.loading')}</p>
      ) : overlays.length === 0 ? (
        <EmptyState>{t('acc.overlays.empty')}</EmptyState>
      ) : (
        <table className="acc-table">
          <thead>
            <tr>
              <th scope="col">{t('acc.overlays.colOverlay')}</th>
              <th scope="col">{t('acc.overlays.colOutputUrl')}</th>
              <th scope="col">{t('acc.overlays.colFormat')}</th><th scope="col"></th>
            </tr>
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

function useFormatLabel(): (sets: number | null) => string {
  const { t } = useI18n();
  return (sets: number | null) => {
    if (sets === 1) return t('acc.format.single');
    if (sets) return t('acc.format.bestOf', { n: sets });
    return t('acc.format.default');
  };
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
  const { t } = useI18n();
  const formatLabel = useFormatLabel();
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
          <a className="acc-btn" href={`/board?oid=${encodeURIComponent(o.oid)}`}>{t('acc.common.open')}</a>{' '}
          <button className="acc-btn ghost" onClick={onCopy}>{copied ? t('acc.common.copied') : t('acc.common.copyUrl')}</button>{' '}
          <button className="acc-btn ghost" onClick={onEdit}>{editing ? t('acc.common.close') : t('acc.common.edit')}</button>{' '}
          <button className="acc-btn danger" onClick={onDelete}>{t('acc.common.delete')}</button>
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
  const { t } = useI18n();
  const { toast } = useToast();
  const [name, setName] = useState(o.display_name || '');
  const [sets, setSets] = useState(o.sets ? String(o.sets) : '');
  const [points, setPoints] = useState(o.points ? String(o.points) : '');
  const [lastSet, setLastSet] = useState(o.points_last_set ? String(o.points_last_set) : '');

  async function save() {
    try {
      await api.updateOverlay(o.oid, {
        display_name: name.trim() || null,
        sets: sets ? Number(sets) : null,
        points: points ? Number(points) : null,
        points_last_set: lastSet ? Number(lastSet) : null,
      });
      onSaved();
      toast(t('acc.overlays.toastSaved'));
    } catch (err) {
      toast(err instanceof api.ApiError ? err.detail : t('acc.overlays.errorSave'), 'error');
    }
  }

  return (
    <div style={{ background: '#14171d', borderRadius: 10, padding: 14, margin: '6px 0' }}>
      <div className="acc-row" style={{ marginBottom: 8 }}>
        <label className="acc-field" style={{ marginBottom: 0 }}>
          <span>{t('acc.overlays.editDisplayName')}</span>
          <input className="acc-input" value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="acc-field" style={{ marginBottom: 0 }}>
          <span>{t('acc.overlays.field.format')}</span>
          <select className="acc-input" value={sets} onChange={(e) => setSets(e.target.value)}>
            <option value="">{t('acc.format.default')}</option>
            <option value="1">{t('acc.format.single')}</option>
            <option value="3">{t('acc.format.bo3')}</option>
            <option value="5">{t('acc.format.bo5')}</option>
          </select>
        </label>
        <label className="acc-field" style={{ marginBottom: 0, maxWidth: 110 }}>
          <span>{t('acc.overlays.editPoints')}</span>
          <input className="acc-input" type="number" value={points} placeholder="25"
            onChange={(e) => setPoints(e.target.value)} />
        </label>
        <label className="acc-field" style={{ marginBottom: 0, maxWidth: 130 }}>
          <span>{t('acc.overlays.editLastSet')}</span>
          <input className="acc-input" type="number" value={lastSet} placeholder="15"
            onChange={(e) => setLastSet(e.target.value)} />
        </label>
      </div>
      <button className="acc-btn" onClick={save}>{t('acc.overlays.editSave')}</button>

      <ControlLink o={o} onChanged={onSaved} />
      <BookmarkLink o={o} onChanged={onSaved} />
    </div>
  );
}

function BookmarkLink({ o, onChanged }: { o: api.OverlayPayload; onChanged: () => void }) {
  const { t } = useI18n();
  const { toast } = useToast();
  const confirm = useConfirm();
  const [busy, setBusy] = useState(false);

  async function toggle() {
    if (!o.public_control) {
      const ok = await confirm({
        title: t('acc.overlays.bookmarkConfirmTitle'),
        message: t('acc.overlays.bookmarkConfirmMsg'),
        confirmLabel: t('acc.common.confirm'),
      });
      if (!ok) return;
    }
    setBusy(true);
    try {
      await api.updateOverlay(o.oid, { public_control: !o.public_control });
      onChanged();
      toast(o.public_control ? t('acc.overlays.bookmarkDisabled') : t('acc.overlays.bookmarkEnabled'));
    } catch (err) {
      toast(err instanceof api.ApiError ? err.detail : t('acc.overlays.bookmarkError'), 'error');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="acc-section" style={{ marginTop: 18, maxWidth: 560 }}>
      <h4 style={{ margin: '0 0 4px' }}>{t('acc.overlays.bookmarkTitle')}</h4>
      <p className="acc-muted" style={{ marginTop: 0 }}>{t('acc.overlays.bookmarkDesc')}</p>
      <label className="acc-muted" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <input type="checkbox" checked={o.public_control} disabled={busy} onChange={toggle} />
        {t('acc.overlays.bookmarkToggle')}
      </label>
      {o.public_control && o.public_control_url && (
        <div style={{ marginTop: 10 }}>
          <CopyField value={o.public_control_url} label={t('acc.overlays.bookmarkLabel')} />
        </div>
      )}
    </div>
  );
}

function ControlLink({ o, onChanged }: { o: api.OverlayPayload; onChanged: () => void }) {
  const { t } = useI18n();
  const { toast } = useToast();
  const confirm = useConfirm();
  const [busy, setBusy] = useState(false);

  async function regenerate() {
    if (o.control_url) {
      const ok = await confirm({
        title: t('acc.overlays.controlConfirmTitle'),
        message: t('acc.overlays.controlConfirmMsg'),
        confirmLabel: t('acc.overlays.controlRegenerate'),
        danger: true,
      });
      if (!ok) return;
    }
    setBusy(true);
    try {
      await api.regenerateControlToken(o.oid);
      onChanged();
      toast(t('acc.overlays.controlToast'));
    } catch (err) {
      toast(err instanceof api.ApiError ? err.detail : t('acc.overlays.controlError'), 'error');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="acc-section" style={{ marginTop: 18, maxWidth: 560 }}>
      <h4 style={{ margin: '0 0 4px' }}>{t('acc.overlays.controlTitle')}</h4>
      <p className="acc-muted" style={{ marginTop: 0 }}>{t('acc.overlays.controlDesc')}</p>
      {o.control_url ? (
        <CopyField value={o.control_url} label={t('acc.overlays.controlTitle')} />
      ) : (
        <span className="acc-muted">{t('acc.overlays.controlNone')}</span>
      )}
      <div style={{ marginTop: 10 }}>
        <button className="acc-btn ghost" onClick={regenerate} disabled={busy}>
          {busy ? t('acc.common.working') : o.control_url ? t('acc.overlays.controlRegenerate') : t('acc.overlays.controlGenerate')}
        </button>
      </div>
    </div>
  );
}
