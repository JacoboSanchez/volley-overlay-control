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

/** One scoreboard, organised around its TWO jobs so each action's purpose is
 *  obvious at a glance:
 *   - OUTPUT — the `/overlay` graphic you paste into OBS once.
 *   - CONTROL — the board where the match is scored: open it yourself, or hand
 *     a no-login link to whoever keeps score.
 *  Rename/Delete are demoted to small management icons in the header. */
function OverlayCard({
  o, onChanged, onDelete,
}: {
  o: api.OverlayPayload;
  onChanged: () => void;
  onDelete: () => void;
}) {
  const { t } = useI18n();
  const [renaming, setRenaming] = useState(false);

  return (
    <section className="acc-overlay-card">
      <header className="acc-overlay-card__head">
        <div className="acc-overlay-card__id">
          <strong className="acc-overlay-card__title">{o.display_name || o.oid}</strong>
          <div className="acc-overlay-card__meta">
            <span className="acc-pill">{o.oid}</span>
            {o.public_control && (
              <span className="acc-pill is-on" title={t('acc.overlays.bookmarkTitle')}>
                {t('acc.overlays.chipBookmark')}
              </span>
            )}
          </div>
        </div>
        <div className="acc-overlay-manage">
          <button
            type="button"
            className={`acc-iconbtn${renaming ? ' is-active' : ''}`}
            aria-pressed={renaming}
            aria-label={t('acc.overlays.rename')}
            title={t('acc.overlays.rename')}
            onClick={() => setRenaming((v) => !v)}
          >
            <span className="material-icons" aria-hidden="true">edit</span>
          </button>
          <button
            type="button"
            className="acc-iconbtn danger"
            aria-label={t('acc.common.delete')}
            title={t('acc.common.delete')}
            onClick={onDelete}
          >
            <span className="material-icons" aria-hidden="true">delete</span>
          </button>
        </div>
      </header>

      {renaming && (
        <RenamePanel o={o} onSaved={() => { setRenaming(false); onChanged(); }} />
      )}

      {/* JOB 1 — the on-stream graphic (paste into OBS once). */}
      <div className="acc-overlay-job">
        <div className="acc-overlay-job__label">
          <span className="material-icons" aria-hidden="true">tv</span>
          {t('acc.overlays.outputLabel')}
        </div>
        <p className="acc-overlay-job__desc acc-muted">{t('acc.overlays.outputDesc')}</p>
        <CopyField value={o.output_url} label={t('acc.overlays.outputLabel')} />
      </div>

      {/* JOB 2 — the scoring board (open mine / share a link). */}
      <div className="acc-overlay-job">
        <div className="acc-overlay-job__label">
          <span className="material-icons" aria-hidden="true">sports_esports</span>
          {t('acc.overlays.controlLabel')}
        </div>
        <p className="acc-overlay-job__desc acc-muted">{t('acc.overlays.controlGroupDesc')}</p>
        <a
          className="acc-btn acc-overlay-open"
          href={`/board?oid=${encodeURIComponent(o.oid)}`}
          target="_blank"
          rel="noopener noreferrer"
        >
          {t('acc.overlays.openBoard')}<span aria-hidden="true"> ↗</span>
        </a>
        <ShareControl o={o} onChanged={onChanged} />
        <BookmarkAdvanced o={o} onChanged={onChanged} />
      </div>
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

/** The shareable, no-login operator link (`/board?c=<token>`). It is minted
 *  with the overlay, so it is shown inline with a Copy button; the small ↻
 *  regenerates it (revoking any previously shared link, behind a confirm). */
function ShareControl({ o, onChanged }: { o: api.OverlayPayload; onChanged: () => void }) {
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
    <div className="acc-overlay-share">
      <div className="acc-overlay-share__label">{t('acc.overlays.shareLabel')}</div>
      {o.control_url ? (
        <div className="acc-overlay-share__row">
          <CopyField value={o.control_url} label={t('acc.overlays.shareLabel')} />
          <button
            type="button"
            className="acc-iconbtn"
            aria-label={t('acc.overlays.controlRegenerate')}
            title={t('acc.overlays.controlRegenerate')}
            onClick={regenerate}
            disabled={busy}
          >
            <span className="material-icons" aria-hidden="true">{busy ? 'hourglass_top' : 'refresh'}</span>
          </button>
        </div>
      ) : (
        <button className="acc-btn ghost" onClick={regenerate} disabled={busy}>
          {busy ? t('acc.common.working') : t('acc.overlays.controlGenerate')}
        </button>
      )}
    </div>
  );
}

/** The permanent, guessable self-bookmark (`/board?u=<user>&oid=<id>`). It is a
 *  niche, opt-in alternative to the shareable link, kept in a collapsed
 *  "Advanced" disclosure so it is never confused with the link you hand out. */
function BookmarkAdvanced({ o, onChanged }: { o: api.OverlayPayload; onChanged: () => void }) {
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
    <details className="acc-overlay-advanced" open={o.public_control}>
      <summary className="acc-overlay-advanced__summary">{t('acc.overlays.advancedTitle')}</summary>
      <div className="acc-overlay-advanced__body">
        <p className="acc-muted" style={{ marginTop: 0 }}>{t('acc.overlays.bookmarkDesc')}</p>
        <label className="acc-muted acc-overlay-advanced__toggle">
          <input type="checkbox" checked={o.public_control} disabled={busy} onChange={toggle} />
          {t('acc.overlays.bookmarkToggle')}
        </label>
        {o.public_control && o.public_control_url && (
          <div style={{ marginTop: 10 }}>
            <CopyField value={o.public_control_url} label={t('acc.overlays.bookmarkLabel')} />
          </div>
        )}
      </div>
    </details>
  );
}
