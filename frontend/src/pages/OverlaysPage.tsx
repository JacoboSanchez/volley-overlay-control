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
  const [error, setError] = useState('');
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
      });
      setOid('');
      setName('');
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
        <div className="acc-overlay-cards">
          {overlays.map((o) => (
            <OverlayCard key={o.oid} o={o} onChanged={load} onDelete={() => onDelete(o)} />
          ))}
        </div>
      )}
    </div>
  );
}

type Panel = 'rename' | 'share' | null;

/** One scoreboard. The card leads with the action you take every match —
 *  opening the control board — and demotes the copy-once browser-source URL and
 *  the occasional share/rename actions below it. */
function OverlayCard({
  o, onChanged, onDelete,
}: {
  o: api.OverlayPayload;
  onChanged: () => void;
  onDelete: () => void;
}) {
  const { t } = useI18n();
  const [panel, setPanel] = useState<Panel>(null);
  const toggle = (p: Exclude<Panel, null>) => setPanel((cur) => (cur === p ? null : p));

  return (
    <section className="acc-overlay-card">
      <header className="acc-overlay-card__head">
        <div className="acc-overlay-card__id">
          <strong className="acc-overlay-card__title">{o.oid}</strong>
          {o.display_name && <div className="acc-muted">{o.display_name}</div>}
        </div>
        <a
          className="acc-btn acc-overlay-open"
          href={`/board?oid=${encodeURIComponent(o.oid)}`}
          target="_blank"
          rel="noopener noreferrer"
        >
          {t('acc.overlays.openBoard')}<span aria-hidden="true"> ↗</span>
        </a>
      </header>

      <div className="acc-overlay-source">
        <div className="acc-overlay-source__label">{t('acc.overlays.sourceLabel')}</div>
        <CopyField value={o.output_url} label={t('acc.overlays.sourceLabel')} />
        <small className="acc-muted">{t('acc.overlays.sourceHint')}</small>
      </div>

      <div className="acc-overlay-card__actions">
        <button
          type="button"
          className={`acc-btn ghost${panel === 'share' ? ' is-active' : ''}`}
          aria-expanded={panel === 'share'}
          onClick={() => toggle('share')}
        >
          {t('acc.overlays.share')}
        </button>
        <button
          type="button"
          className={`acc-btn ghost${panel === 'rename' ? ' is-active' : ''}`}
          aria-expanded={panel === 'rename'}
          onClick={() => toggle('rename')}
        >
          {t('acc.overlays.rename')}
        </button>
        <button type="button" className="acc-btn danger" onClick={onDelete}>{t('acc.common.delete')}</button>
      </div>

      {panel === 'rename' && (
        <RenamePanel o={o} onSaved={() => { setPanel(null); onChanged(); }} />
      )}
      {panel === 'share' && (
        <div className="acc-overlay-panel">
          <ControlLink o={o} onChanged={onChanged} />
          <BookmarkLink o={o} onChanged={onChanged} />
        </div>
      )}
    </section>
  );
}

function RenamePanel({ o, onSaved }: { o: api.OverlayPayload; onSaved: () => void }) {
  const { t } = useI18n();
  const { toast } = useToast();
  const [name, setName] = useState(o.display_name || '');

  async function save() {
    try {
      await api.updateOverlay(o.oid, { display_name: name.trim() || null });
      onSaved();
      toast(t('acc.overlays.toastSaved'));
    } catch (err) {
      toast(err instanceof api.ApiError ? err.detail : t('acc.overlays.errorSave'), 'error');
    }
  }

  return (
    <div className="acc-overlay-panel">
      <label className="acc-field" style={{ marginBottom: 8 }}>
        <span>{t('acc.overlays.editDisplayName')}</span>
        <input className="acc-input" value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      <button className="acc-btn" onClick={save}>{t('acc.overlays.editSave')}</button>
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
