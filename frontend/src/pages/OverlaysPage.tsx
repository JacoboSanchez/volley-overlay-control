import { type FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import * as api from '../api/overlays';
import CopyField from '../components/CopyField';
import EmptyState from '../components/EmptyState';
import { useToast } from '../components/Toast';
import { useConfirm } from '../components/ConfirmProvider';
import { useOverlays } from '../hooks/useOverlays';
import { useI18n } from '../i18n';
import { apiErrorMessage } from '../hooks/useAsyncAction';

const OVERLAY_TOOLS_THRESHOLD = 6;

export default function OverlaysPage() {
  const { t } = useI18n();
  const { toast } = useToast();
  const confirm = useConfirm();
  const { overlays, loading, error: loadError, reload } = useOverlays();
  const [oid, setOid] = useState('');
  const [description, setDescription] = useState('');
  const [creating, setCreating] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [favoritesOnly, setFavoritesOnly] = useState(false);
  const [newOverlayOid, setNewOverlayOid] = useState<string | null>(null);
  // Create errors are shown inline above the list but must not hide the list
  // (it is still valid); load errors are handled separately via ``loadError``.
  const [createError, setCreateError] = useState('');

  // Mirror of the backend rule (app/id_validation.py OVERLAY_ID_PATTERN) so
  // an invalid id is rejected inline instead of round-tripping to a 4xx.
  const OID_RE = /^(?!\.{1,2}$)[A-Za-z0-9._-]{1,64}$/;

  // A first-time user should land directly in the only useful empty-state
  // action. Once overlays exist, keep this occasional form out of the way so
  // opening an existing scoreboard remains above the fold.
  useEffect(() => {
    if (!loading && !loadError && overlays.length === 0) setCreateOpen(true);
  }, [loadError, loading, overlays.length]);

  const favoriteCount = overlays.filter((overlay) => overlay.is_favorite).length;
  const visibleOverlays = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    return overlays
      .filter((overlay) => {
        if (favoritesOnly && !overlay.is_favorite) return false;
        if (!needle) return true;
        return `${overlay.description ?? ''}\n${overlay.oid}`.toLocaleLowerCase().includes(needle);
      })
      .sort((a, b) => Number(b.is_favorite) - Number(a.is_favorite) || a.oid.localeCompare(b.oid));
  }, [favoritesOnly, overlays, query]);

  // Removing the final favorite should not strand the user on an empty,
  // apparently broken list.
  useEffect(() => {
    if (favoritesOnly && favoriteCount === 0) setFavoritesOnly(false);
  }, [favoriteCount, favoritesOnly]);

  // Keep the post-create emphasis transient; the direct actions remain after
  // the highlight fades.
  useEffect(() => {
    if (!newOverlayOid) return;
    const timeout = window.setTimeout(() => setNewOverlayOid(null), 4500);
    return () => window.clearTimeout(timeout);
  }, [newOverlayOid]);

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    if (creating) return;
    setCreateError('');
    if (!OID_RE.test(oid.trim())) {
      setCreateError(t('acc.overlays.field.oidHelp'));
      return;
    }
    setCreating(true);
    try {
      const created = oid.trim();
      await api.createOverlay(created, {
        description: description.trim() || null,
      });
      setOid('');
      setDescription('');
      await reload();
      setCreateOpen(false);
      setQuery('');
      setFavoritesOnly(false);
      setNewOverlayOid(created);
      toast(t('acc.overlays.toastCreated', { oid: created }));
    } catch (err) {
      setCreateError(apiErrorMessage(err, t('acc.overlays.errorCreate')));
    } finally {
      setCreating(false);
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
      await reload();
      toast(t('acc.overlays.toastDeleted', { oid: o.oid }));
    } catch (err) {
      toast(apiErrorMessage(err, t('acc.overlays.errorDelete')), 'error');
    }
  }

  async function onToggleFavorite(o: api.OverlayPayload) {
    try {
      await api.updateOverlay(o.oid, { is_favorite: !o.is_favorite });
      await reload();
      toast(
        o.is_favorite
          ? t('acc.overlays.toastFavoriteRemoved', { oid: o.oid })
          : t('acc.overlays.toastFavoriteAdded', { oid: o.oid }),
      );
    } catch (err) {
      toast(apiErrorMessage(err, t('acc.overlays.errorFavorite')), 'error');
    }
  }

  return (
    <div>
      <div className="acc-overlays-titlebar">
        <div>
          <h2>{t('acc.nav.overlays')}</h2>
          <p className="acc-muted">{t('acc.overlays.intro')}</p>
        </div>
        <button
          type="button"
          className={`acc-btn${createOpen ? ' ghost' : ''}`}
          aria-expanded={createOpen}
          onClick={() => {
            setCreateError('');
            setCreateOpen((value) => !value);
          }}
        >
          <span className="material-icons" aria-hidden="true">
            {createOpen ? 'close' : 'add'}
          </span>
          {createOpen ? t('acc.common.cancel') : t('acc.overlays.new')}
        </button>
      </div>

      {createOpen && (
        <form className="acc-form acc-overlay-create" onSubmit={onCreate}>
          <label className="acc-field">
            <span>{t('acc.overlays.field.oid')}</span>
            <input
              className="acc-input"
              value={oid}
              placeholder={t('acc.overlays.field.oidPlaceholder')}
              maxLength={64}
              // eslint-disable-next-line jsx-a11y/no-autofocus -- the user explicitly opened this inline creation form
              autoFocus
              onChange={(e) => setOid(e.target.value)}
            />
            <small className="acc-muted">{t('acc.overlays.field.oidHelp')}</small>
          </label>
          <label className="acc-field">
            <span>{t('acc.overlays.field.description')}</span>
            <input
              className="acc-input"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </label>
          <div className="acc-form-actions">
            <span className="acc-form-spacer" aria-hidden="true">
              &nbsp;
            </span>
            <button className="acc-btn" type="submit" disabled={!oid.trim() || creating}>
              {creating ? t('acc.common.working') : t('acc.overlays.add')}
            </button>
          </div>
        </form>
      )}
      {(createError || loadError) && (
        <div className="acc-error">{createError || t('acc.reports.errorOverlays')}</div>
      )}

      {loading ? (
        <p className="acc-muted">{t('acc.common.loading')}</p>
      ) : loadError ? null /* the error banner above already explains the failure */ : overlays.length ===
        0 ? (
        <EmptyState>{t('acc.overlays.empty')}</EmptyState>
      ) : (
        <>
          {overlays.length >= OVERLAY_TOOLS_THRESHOLD && (
            <div className="acc-overlay-toolbar">
              <label className="acc-overlay-search">
                <span className="material-icons" aria-hidden="true">
                  search
                </span>
                <input
                  className="acc-input"
                  type="search"
                  value={query}
                  aria-label={t('acc.overlays.searchLabel')}
                  placeholder={t('acc.overlays.searchPlaceholder')}
                  onChange={(event) => setQuery(event.target.value)}
                />
              </label>
              <button
                type="button"
                className={`acc-btn ghost acc-overlay-favorites-filter${favoritesOnly ? ' is-active' : ''}`}
                aria-pressed={favoritesOnly}
                disabled={favoriteCount === 0}
                onClick={() => setFavoritesOnly((value) => !value)}
              >
                <span className="material-icons" aria-hidden="true">
                  star
                </span>
                {t('acc.overlays.favoritesOnly')}
                {favoriteCount > 0 && <span className="acc-pill">{favoriteCount}</span>}
              </button>
              <span className="acc-overlay-result-count acc-muted">
                {t('acc.overlays.resultCount', {
                  visible: visibleOverlays.length,
                  total: overlays.length,
                })}
              </span>
            </div>
          )}

          {visibleOverlays.length === 0 ? (
            <div className="acc-empty">
              <div>{t('acc.overlays.noMatches')}</div>
              <div className="acc-empty-action">
                <button
                  type="button"
                  className="acc-btn ghost"
                  onClick={() => {
                    setQuery('');
                    setFavoritesOnly(false);
                  }}
                >
                  {t('acc.overlays.clearFilters')}
                </button>
              </div>
            </div>
          ) : (
            <div className="acc-overlay-cards">
              {visibleOverlays.map((o) => (
                <OverlayCard
                  key={o.oid}
                  o={o}
                  highlighted={o.oid === newOverlayOid}
                  onChanged={reload}
                  onDelete={() => onDelete(o)}
                  onToggleFavorite={() => onToggleFavorite(o)}
                />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

/** One scoreboard. Its two frequent actions stay available while collapsed:
 *  controlling the match and checking the visual overlay. The disclosure is
 *  reserved for copy-once links and occasional settings, keeping a long list
 *  scannable without making the operator drill into every card. */
function OverlayCard({
  o,
  highlighted,
  onChanged,
  onDelete,
  onToggleFavorite,
}: {
  o: api.OverlayPayload;
  highlighted: boolean;
  onChanged: () => void;
  onDelete: () => void;
  onToggleFavorite: () => void;
}) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [renaming, setRenaming] = useState(false);

  return (
    <section
      className={`acc-overlay-card${open ? ' is-open' : ''}${highlighted ? ' is-new' : ''}`}
      data-overlay-oid={o.oid}
    >
      <header className="acc-overlay-card__head">
        <div className="acc-overlay-headtext">
          <div className="acc-overlay-titlerow">
            <strong className="acc-overlay-card__title">{o.description || o.oid}</strong>
            {o.is_favorite && (
              <span className="acc-overlay-favorite" title={t('acc.overlays.favoriteTitle')}>
                <span className="material-icons" aria-hidden="true">
                  star
                </span>
              </span>
            )}
            {o.public_control && (
              <span className="acc-pill is-on" title={t('acc.overlays.bookmarkTitle')}>
                {t('acc.overlays.chipBookmark')}
              </span>
            )}
          </div>
          {o.description && (
            <span className="acc-overlay-card__desc">
              {t('acc.overlays.idMeta', { oid: o.oid })}
            </span>
          )}
        </div>
        <div className="acc-overlay-quick-actions">
          <a
            className="acc-btn acc-overlay-control"
            href={`/board?oid=${encodeURIComponent(o.oid)}`}
            target="_blank"
            rel="noopener noreferrer"
          >
            <span className="material-icons" aria-hidden="true">
              sports_esports
            </span>
            {t('acc.overlays.openBoard')}
          </a>
          <a
            className="acc-btn secondary acc-overlay-view"
            href={o.output_url}
            target="_blank"
            rel="noopener noreferrer"
          >
            <span className="material-icons" aria-hidden="true">
              open_in_new
            </span>
            {t('acc.overlays.viewOverlay')}
          </a>
          <OverlayManageMenu
            active={renaming}
            isFavorite={o.is_favorite}
            onEdit={() => {
              setOpen(true);
              setRenaming((value) => !value);
            }}
            onToggleFavorite={onToggleFavorite}
            onDelete={onDelete}
          />
        </div>
      </header>

      <button
        type="button"
        className="acc-overlay-details-toggle"
        aria-expanded={open}
        onClick={() => {
          if (open) setRenaming(false);
          setOpen((value) => !value);
        }}
      >
        <span className="material-icons" aria-hidden="true">
          {open ? 'expand_less' : 'expand_more'}
        </span>
        {t('acc.overlays.linksSettings')}
      </button>

      {open && (
        <div className="acc-overlay-body">
          {renaming && (
            <RenamePanel
              o={o}
              onSaved={() => {
                setRenaming(false);
                onChanged();
              }}
            />
          )}

          {/* The operator share link is used more often than the copy-once OBS
              URL, so it leads the details panel. */}
          <div className="acc-overlay-job">
            <div className="acc-overlay-job__label">
              <span className="material-icons" aria-hidden="true">
                share
              </span>
              {t('acc.overlays.controlLabel')}
            </div>
            <p className="acc-overlay-job__desc acc-muted">{t('acc.overlays.controlGroupDesc')}</p>
            <ShareControl o={o} onChanged={onChanged} />
            <BookmarkAdvanced o={o} onChanged={onChanged} />
          </div>

          {/* The OBS graphic is normally configured once, but remains easy to
              copy or open from the quick action above. */}
          <div className="acc-overlay-job">
            <div className="acc-overlay-job__label">
              <span className="material-icons" aria-hidden="true">
                tv
              </span>
              {t('acc.overlays.outputLabel')}
            </div>
            <p className="acc-overlay-job__desc acc-muted">{t('acc.overlays.outputDesc')}</p>
            <CopyField value={o.output_url} label={t('acc.overlays.outputLabel')} multiline />
          </div>
        </div>
      )}
    </section>
  );
}

function OverlayManageMenu({
  active,
  isFavorite,
  onEdit,
  onToggleFavorite,
  onDelete,
}: {
  active: boolean;
  isFavorite: boolean;
  onEdit: () => void;
  onToggleFavorite: () => void;
  onDelete: () => void;
}) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const closeOutside = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      setOpen(false);
      triggerRef.current?.focus();
    };
    document.addEventListener('pointerdown', closeOutside);
    document.addEventListener('keydown', closeOnEscape);
    return () => {
      document.removeEventListener('pointerdown', closeOutside);
      document.removeEventListener('keydown', closeOnEscape);
    };
  }, [open]);

  return (
    <div className="acc-overlay-manage" ref={rootRef}>
      <button
        ref={triggerRef}
        type="button"
        className={`acc-iconbtn${active ? ' is-active' : ''}`}
        aria-label={t('acc.overlays.moreActions')}
        title={t('acc.overlays.moreActions')}
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <span className="material-icons" aria-hidden="true">
          more_vert
        </span>
      </button>
      {open && (
        <div
          className="acc-overlay-manage__menu"
          role="group"
          aria-label={t('acc.overlays.moreActions')}
        >
          <button
            type="button"
            onClick={() => {
              setOpen(false);
              onToggleFavorite();
            }}
          >
            <span className="material-icons" aria-hidden="true">
              {isFavorite ? 'star' : 'star_border'}
            </span>
            {isFavorite ? t('acc.overlays.favoriteRemove') : t('acc.overlays.favoriteAdd')}
          </button>
          <button
            type="button"
            onClick={() => {
              setOpen(false);
              onEdit();
            }}
          >
            <span className="material-icons" aria-hidden="true">
              edit
            </span>
            {t('acc.overlays.rename')}
          </button>
          <button
            type="button"
            className="danger"
            onClick={() => {
              setOpen(false);
              onDelete();
            }}
          >
            <span className="material-icons" aria-hidden="true">
              delete
            </span>
            {t('acc.common.delete')}
          </button>
        </div>
      )}
    </div>
  );
}

function RenamePanel({ o, onSaved }: { o: api.OverlayPayload; onSaved: () => void }) {
  const { t } = useI18n();
  const { toast } = useToast();
  const [description, setDescription] = useState(o.description || '');
  const [busy, setBusy] = useState(false);

  async function save() {
    if (busy) return;
    setBusy(true);
    try {
      await api.updateOverlay(o.oid, { description: description.trim() || null });
      onSaved();
      toast(t('acc.overlays.toastSaved'));
    } catch (err) {
      toast(apiErrorMessage(err, t('acc.overlays.errorSave')), 'error');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="acc-overlay-panel">
      <label className="acc-field" style={{ marginBottom: 8 }}>
        <span>{t('acc.overlays.editDescription')}</span>
        <input
          className="acc-input"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </label>
      <button className="acc-btn" onClick={save} disabled={busy}>
        {busy ? t('acc.common.working') : t('acc.overlays.editSave')}
      </button>
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
      toast(apiErrorMessage(err, t('acc.overlays.controlError')), 'error');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="acc-overlay-share">
      {/* The regenerate control lives on the label line, not next to the URL:
          it acts on the link as a whole (revoke + remint), so it reads as
          part of the heading, and the URL block below keeps the full width. */}
      <div className="acc-overlay-share__head">
        <span className="acc-overlay-share__label">{t('acc.overlays.shareLabel')}</span>
        {o.control_url && (
          <button
            type="button"
            className="acc-overlay-share__regen"
            aria-label={t('acc.overlays.controlRegenerate')}
            title={t('acc.overlays.controlRegenerate')}
            onClick={regenerate}
            disabled={busy}
          >
            <span className="material-icons" aria-hidden="true">
              {busy ? 'hourglass_top' : 'refresh'}
            </span>
          </button>
        )}
      </div>
      {o.control_url ? (
        <CopyField value={o.control_url} label={t('acc.overlays.shareLabel')} multiline />
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
      toast(
        o.public_control ? t('acc.overlays.bookmarkDisabled') : t('acc.overlays.bookmarkEnabled'),
      );
    } catch (err) {
      toast(apiErrorMessage(err, t('acc.overlays.bookmarkError')), 'error');
    } finally {
      setBusy(false);
    }
  }

  return (
    <details className="acc-overlay-advanced" open={o.public_control}>
      <summary className="acc-overlay-advanced__summary">{t('acc.overlays.advancedTitle')}</summary>
      <div className="acc-overlay-advanced__body">
        <p className="acc-muted" style={{ marginTop: 0 }}>
          {t('acc.overlays.bookmarkDesc')}
        </p>
        <label className="acc-muted acc-overlay-advanced__toggle">
          <input type="checkbox" checked={o.public_control} disabled={busy} onChange={toggle} />
          {t('acc.overlays.bookmarkToggle')}
        </label>
        {o.public_control && o.public_control_url && (
          <div style={{ marginTop: 10 }}>
            <CopyField
              value={o.public_control_url}
              label={t('acc.overlays.bookmarkLabel')}
              multiline
            />
          </div>
        )}
      </div>
    </details>
  );
}
